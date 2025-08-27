import sys, json, time
from paho.mqtt.client import Client

def main():
    if len(sys.argv) != 3:
        print("Usage: python tools/publish.py <topic> <json-file>")
        sys.exit(1)
    topic, path = sys.argv[1], sys.argv[2]
    payload = json.loads(open(path, "r", encoding="utf-8").read())

    client = Client(client_id="tools-publisher", clean_session=True)
    client.connect("127.0.0.1", 1883, keepalive=30)
    client.loop_start()
    info = client.publish(topic, json.dumps(payload), qos=1)
    info.wait_for_publish()
    client.loop_stop()
    client.disconnect()
    print(f"Published to {topic}: {payload}")

if __name__ == "__main__":
    main()
