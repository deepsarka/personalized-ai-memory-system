import json
from confluent_kafka import Producer

conf = {
    'bootstrap.servers': 'dafs0vhq9rmp2phfm6tg.any.ap-south-1.mpx.prd.cloud.redpanda.com:9092',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanism': 'SCRAM-SHA-256',
    'sasl.username': 'Spotify',
    'sasl.password': 'L0IFXvdlx1vauFi1oZ3sz26Rqg33HE',
}

producer = Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")

event = {
    "user_id": "spotify_user_1",
    "action": "play_track",
    "track_id": "4cOdK2wGLETKBW3PvgPWqT"
}

producer.produce(
    topic='interaction-events',
    value=json.dumps(event).encode('utf-8'),
    callback=delivery_report
)

producer.flush()