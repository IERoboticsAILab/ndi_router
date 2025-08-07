# NDI Router

A Python service for discovering and monitoring NDI sources on your network.

## Prerequisites

1. Install NewTek NDI Tools and SDK:
   - Download from [NewTek NDI Tools](https://www.ndi.tv/tools/)
   - Install both NDI Tools and NDI SDK

2. Set up environment variables:
   - Set `NDILIB_REDIST_PATH` to point to your NDI SDK libraries
   - Example: `NDILIB_REDIST_PATH=C:\Program Files\NewTek\NDI SDK for Windows\Lib\x64`

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/ndi_router.git
   cd ndi_router
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the NDI discovery service:
```bash
python ndi_discovery.py
```

The service will:
- Scan for NDI sources every 5 seconds
- Display discovered sources with their metadata
- Continue running until interrupted (Ctrl+C)

## Features

- Dynamic NDI source discovery
- Source metadata including:
  - Source name
  - IP address
  - Device name
  - URL address
- Configurable scan interval
- Error handling and graceful shutdown

## Development

To use the `NDIDiscovery` class in your own code:

```python
from ndi_discovery import NDIDiscovery

# Create discovery instance with custom scan interval (in seconds)
discovery = NDIDiscovery(scan_interval=10)

# Start continuous discovery
discovery.start_discovery()

# Or scan once
sources = discovery.scan_sources()
```

## License

MIT License