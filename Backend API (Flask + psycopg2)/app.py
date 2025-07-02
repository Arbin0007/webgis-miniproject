from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
import json

app = Flask(__name__)
CORS(app)

conn = psycopg2.connect(dbname="site_selection_db", user="postgres", password="2247", host="localhost", port="5433")

def fetch_geojson(query, params=None):
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    features = []
    for row in rows:
        geom = row[0]
        props = row[1]
        features.append({
            "type": "Feature",
            "geometry": json.loads(geom),
            "properties": props
        })
    cur.close()
    return {
        "type": "FeatureCollection",
        "features": features
    }

@app.route('/layers/<layer>')
def get_layer(layer):
    if layer not in ['landuse', 'popdensity', 'roads']:
        return jsonify({"error": "Invalid layer"}), 400
    query = f"""
    SELECT ST_AsGeoJSON(geom), row_to_json(t) FROM {layer} as t;
    """
    return jsonify(fetch_geojson(query))

@app.route('/spatial/buffer', methods=['POST'])
def buffer_road():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    road_id = data.get('id')
    distance = data.get('distance', 500)
    query = """
    SELECT ST_AsGeoJSON(ST_Buffer(geom::geography, %s)::geometry), row_to_json(t)
    FROM roads as t WHERE id = %s;
    """
    cur = conn.cursor()
    cur.execute(query, (distance, road_id))
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify({"error": "Road not found"}), 404
    geom, props = row
    cur.close()
    return jsonify({"type": "Feature", "geometry": json.loads(geom), "properties": props})

@app.route('/spatial/intersect', methods=['POST'])
def intersect_analysis():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    buffer_geojson = json.dumps(data.get('buffer_geom'))
    query = """
    SELECT ST_AsGeoJSON(l.geom), row_to_json(l)
    FROM landuse l
    WHERE ST_Intersects(l.geom, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
    """
    return jsonify(fetch_geojson(query, (buffer_geojson,)))

@app.route('/attribute/query', methods=['GET'])
def attribute_query():
    layer = request.args.get('layer')
    attr = request.args.get('attr')
    op = request.args.get('op')
    val = request.args.get('val')
    if layer not in ['landuse', 'popdensity']:
        return jsonify({"error": "Invalid layer"}), 400
    allowed_ops = ['=', '>', '<', '>=', '<=', 'LIKE']
    if op not in allowed_ops:
        return jsonify({"error": "Invalid operator"}), 400
    if op == 'LIKE':
        val = f"%{val}%"
    query = f"""
    SELECT ST_AsGeoJSON(geom), row_to_json(t)
    FROM {layer} as t
    WHERE {attr} {op} %s;
    """
    return jsonify(fetch_geojson(query, (val,)))

if __name__ == '__main__':
    app.run(debug=True)
