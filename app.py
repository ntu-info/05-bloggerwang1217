# app.py
from flask import Flask, jsonify, abort, send_file
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

_engine = None

def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    db_url = os.getenv("DB_URL")
    if not db_url:
        raise RuntimeError("Missing DB_URL (or DATABASE_URL) environment variable.")
    # Normalize old 'postgres://' scheme to 'postgresql://'
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]
    # Ensure new connections default to the ns schema
    _engine = create_engine(
        db_url,
        pool_pre_ping=True,
        connect_args={"options": "-csearch_path=ns,public"},
    )
    return _engine

def create_app():
    app = Flask(__name__)

    @app.get("/", endpoint="health")
    def health():
        return "<p>Server working!</p>"

    @app.get("/img", endpoint="show_img")
    def show_img():
        return send_file("amygdala.gif", mimetype="image/gif")

    @app.get("/terms/<term>/studies", endpoint="terms_studies")
    def get_studies_by_term(term):
        return term

    @app.get("/locations/<coords>/studies", endpoint="locations_studies")
    def get_studies_by_coordinates(coords):
        x, y, z = map(int, coords.split("_"))
        return jsonify([x, y, z])

    @app.get("/dissociate/terms/<term_a>/<term_b>", endpoint="dissociate_terms")
    def dissociate_terms(term_a, term_b):
        # Get DB engine
        eng = get_engine()

        # Query for studies that mention term_a but do NOT mention term_b
        # Include study titles from metadata table
        with eng.begin() as conn:
            # Ensure schema
            conn.execute(text("SET search_path TO ns, public;"))

            # Use tsvector/plainto_tsquery to match normalized terms (handles tfidf prefixes)
            # Replace underscores with spaces when building the tsquery.
            rows = conn.execute(text(
                """
                SELECT DISTINCT at.study_id, m.title
                FROM ns.annotations_terms at
                LEFT JOIN ns.metadata m ON at.study_id = m.study_id
                WHERE to_tsvector('english', regexp_replace(at.term, '^terms_[^_]+__', '', 'g'))
                      @@ plainto_tsquery('english', :term_a)
                  AND NOT EXISTS (
                      SELECT 1 FROM ns.annotations_terms at2
                      WHERE at2.study_id = at.study_id
                        AND to_tsvector('english', regexp_replace(at2.term, '^terms_[^_]+__', '', 'g'))
                            @@ plainto_tsquery('english', :term_b)
                  )
                LIMIT 100
                """
            ), {"term_a": term_a.replace("_", " "), "term_b": term_b.replace("_", " ")}).all()

            results = [{"study_id": r[0], "title": r[1]} for r in rows]

            # Return list of studies with titles
            return jsonify(results)

    @app.get("/dissociate/locations/<coords_a>/<coords_b>", endpoint="dissociate_locations")
    def dissociate_locations(coords_a, coords_b):
        # Parse MNI coordinates from 'x_y_z' strings
        x1, y1, z1 = map(float, coords_a.split("_"))
        x2, y2, z2 = map(float, coords_b.split("_"))

        # Get DB engine
        eng = get_engine()

        # Use PostGIS ST_DWithin to find studies that have a coordinate near point A
        # but not near point B. Radius is in the same units as geom (default 8 mm).
        radius = 8
        with eng.begin() as conn:
            conn.execute(text("SET search_path TO ns, public;"))
            # Use SRID-aware points to avoid geometry type / SRID mismatches
            rows = conn.execute(text(
                """
                SELECT DISTINCT c1.study_id, m.title
                FROM ns.coordinates c1
                LEFT JOIN ns.metadata m ON c1.study_id = m.study_id
                WHERE ST_DWithin(c1.geom, ST_SetSRID(ST_MakePoint(:x1, :y1, :z1), ST_SRID(c1.geom)), :radius)
                    AND NOT EXISTS (
                        SELECT 1 FROM ns.coordinates c2
                        WHERE c2.study_id = c1.study_id
                            AND ST_DWithin(c2.geom, ST_SetSRID(ST_MakePoint(:x2, :y2, :z2), ST_SRID(c2.geom)), :radius)
                    )
                LIMIT 200
                """
            ), {"x1": x1, "y1": y1, "z1": z1, "x2": x2, "y2": y2, "z2": z2, "radius": radius}).all()

            results = [{"study_id": r[0], "title": r[1]} for r in rows]
            # Return list of studies with titles
            return jsonify(results)

    @app.get("/test_db", endpoint="test_db")
    
    def test_db():
        eng = get_engine()
        payload = {"ok": False, "dialect": eng.dialect.name}

        try:
            with eng.begin() as conn:
                # Ensure we are in the correct schema
                conn.execute(text("SET search_path TO ns, public;"))
                payload["version"] = conn.exec_driver_sql("SELECT version()").scalar()

                # Counts
                payload["coordinates_count"] = conn.execute(text("SELECT COUNT(*) FROM ns.coordinates")).scalar()
                payload["metadata_count"] = conn.execute(text("SELECT COUNT(*) FROM ns.metadata")).scalar()
                payload["annotations_terms_count"] = conn.execute(text("SELECT COUNT(*) FROM ns.annotations_terms")).scalar()

                # Samples
                try:
                    rows = conn.execute(text(
                        "SELECT study_id, ST_X(geom) AS x, ST_Y(geom) AS y, ST_Z(geom) AS z FROM ns.coordinates LIMIT 3"
                    )).mappings().all()
                    payload["coordinates_sample"] = [dict(r) for r in rows]
                except Exception:
                    payload["coordinates_sample"] = []

                try:
                    # Select a few columns if they exist; otherwise select a generic subset
                    rows = conn.execute(text("SELECT * FROM ns.metadata LIMIT 3")).mappings().all()
                    payload["metadata_sample"] = [dict(r) for r in rows]
                except Exception:
                    payload["metadata_sample"] = []

                try:
                    rows = conn.execute(text(
                        "SELECT study_id, contrast_id, term, weight FROM ns.annotations_terms LIMIT 3"
                    )).mappings().all()
                    payload["annotations_terms_sample"] = [dict(r) for r in rows]
                except Exception:
                    payload["annotations_terms_sample"] = []

            payload["ok"] = True
            return jsonify(payload), 200

        except Exception as e:
            payload["error"] = str(e)
            return jsonify(payload), 500

    return app

# WSGI entry point (no __main__)
app = create_app()
