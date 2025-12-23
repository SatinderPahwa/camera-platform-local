# Camera Livestreaming - Quick Start

## 🚀 Fastest Way to Test

```bash
cd /Users/satinder/Documents/_camera_firmware/camera_project/livestreaming

# 1. Start all services (automatic setup)
./start_all.sh

# 2. Test with Camera 4
./test_stream.sh

# 3. View in browser (opens automatically)
# http://localhost:5000/livestream/viewer?camera=56C1CADCF1FA4C6CAEBA3E2FD85EFEBF
```

That's it! The scripts handle everything automatically.

## 📋 Available Scripts

| Script | Description |
|--------|-------------|
| `./start_all.sh` | Start all services (Kurento + API + Signaling + Dashboard) |
| `./stop_all.sh` | Stop all services |
| `./status.sh` | Check status of all services |
| `./test_stream.sh` | Complete test with Camera 4 |

## 🔍 Quick Commands

```bash
# Check health
curl http://localhost:8080/health | python3 -m json.tool

# List active streams
curl http://localhost:8080/streams | python3 -m json.tool

# Start stream manually
curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/start

# Stop stream manually
curl -X POST http://localhost:8080/streams/56C1CADCF1FA4C6CAEBA3E2FD85EFEBF/stop

# View logs
tail -f logs/livestreaming.log

# Check Kurento
podman logs -f kms-production
```

## 🌐 Service URLs

- **API:** http://localhost:8080
- **Signaling:** ws://localhost:8765
- **Dashboard:** http://localhost:5000
- **Kurento:** ws://localhost:8888/kurento

## 📖 Full Documentation

- **SETUP.md** - Complete setup and troubleshooting guide
- **README.md** - Architecture and API documentation
- **IMPLEMENTATION_SUMMARY.md** - What was built

## ⚠️ Prerequisites

- Python 3.8+
- Podman
- AWS CLI (configured)

The `start_all.sh` script checks these automatically.

## 🧪 Expected Test Results

When running `./test_stream.sh`, you should see:

✅ Stream starts successfully
✅ No timeout after 30 seconds (REMB working!)
✅ Keepalives sent every 4 seconds
✅ Zero errors
✅ Stream runs for 10+ minutes

## 🆘 Troubleshooting

```bash
# Check what's running
./status.sh

# View logs
tail -f logs/livestreaming.log
tail -f logs/main.out

# Restart everything
./stop_all.sh
./start_all.sh
```

## 🎯 Key Features

- ✅ Automatic REMB packet handling (prevents 30s timeout)
- ✅ AWS IoT keepalive messages every 4 seconds
- ✅ Multiple viewers per stream
- ✅ Real-time statistics
- ✅ Browser-based viewing
- ✅ Production-ready architecture

---

**Need help?** See SETUP.md for detailed documentation.
