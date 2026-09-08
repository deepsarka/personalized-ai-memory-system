import json
from confluent_kafka import Consumer, KafkaError

conf = {
    'bootstrap.servers': 'dafs0vhq9rmp2phfm6tg.any.ap-south-1.mpx.prd.cloud.redpanda.com:9092',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanism': 'SCRAM-SHA-256',
    'sasl.username': 'Spotify',
    'sasl.password': 'L0IFXvdlx1vauFi1oZ3sz26Rqg33HE',
    'group.id': 'stage2-processor',
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(conf)
consumer.subscribe(['interaction-events'])

try:
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            else:
                print(msg.error())
                break

        data = json.loads(msg.value().decode('utf-8'))
        print(f"Received event: {data} from offset {msg.offset()}")

except KeyboardInterrupt:
    pass
finally:
    consumer.close()