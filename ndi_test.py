import time
from cyndilib.finder import Finder
from cyndilib.receiver import Receiver

def list_ndi_sources_with_details(timeout=3.0):
    finder = Finder()
    finder.open()

    end_time = time.time() + timeout
    while time.time() < end_time:
        changed = finder.wait_for_sources(timeout=end_time - time.time())
        if changed:
            finder.update_sources()
        time.sleep(0.1)

    results = []
    for src in finder.iter_sources():
        receiver = Receiver()
        receiver.set_source(src)     # Step 1: set the source
        receiver.reconnect()         # Step 2: reconnect to it

        frame = receiver.receive(1000, 0)
        if frame and frame.get('video'):
            video = frame['video']
            resolution = f"{video['width']}x{video['height']}"
            framerate = video['framerate_numerator'] / video['framerate_denominator']
        else:
            resolution = "?"
            framerate = 0.0

        results.append({
            "name": src.name,
            "host": src.host_name,
            "stream": src.stream_name,
            "resolution": resolution,
            "framerate": f"{framerate:.2f} fps"
        })

        receiver.disconnect()

    finder.close()
    return results

if __name__ == "__main__":
    sources = list_ndi_sources_with_details()
    for src in sources:
        print(src)