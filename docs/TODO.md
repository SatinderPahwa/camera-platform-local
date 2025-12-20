# TODO - Future Improvements

## High Priority

### Replace Flask Development Server with Production WSGI Server

**Current Issue:**
```
WARNING: This is a development server. Do not use it in a production deployment.
Use a production WSGI server instead.
```

**Problem:**
- Flask dev server accumulates CLOSE-WAIT connections
- Not designed for production load
- Single-threaded, not optimized for concurrent requests
- Connection leak issues require scheduled restarts

**Recommended Solution:**
Replace Flask dev server with **Gunicorn** or **uWSGI**

**Implementation Steps:**

1. **Install Gunicorn:**
   ```bash
   pip install gunicorn
   pip freeze > requirements.txt
   ```

2. **Update managed_start.sh:**
   ```bash
   # Replace:
   python3 dashboard_server.py

   # With:
   gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 --access-logfile logs/gunicorn_access.log --error-logfile logs/gunicorn_error.log dashboard_server:app
   ```

3. **Benefits:**
   - Multiple worker processes (handles concurrent requests)
   - Proper connection management (no CLOSE-WAIT leaks)
   - Production-grade performance
   - Better resource utilization
   - May eliminate need for scheduled restarts

**References:**
- Gunicorn: https://gunicorn.org/
- Flask deployment: https://flask.palletsprojects.com/en/latest/deploying/

**Status:** Not started (wait until platform is fully operational)

---

## Medium Priority

### Add Rate Limiting

**Problem:**
Dashboard and config server exposed to network without rate limiting

**Solution:**
- Add Flask-Limiter for API endpoints
- Configure nginx rate limiting
- Prevent DoS attacks

### Implement Connection Timeouts

**Problem:**
Long-running connections may not close properly

**Solution:**
- Add socket timeout configuration
- Implement connection pooling
- Add request timeout middleware

### Add Prometheus Metrics

**Problem:**
Limited visibility into system performance

**Solution:**
- Add prometheus_flask_exporter
- Track request rates, latencies, error rates
- Monitor EMQX metrics
- Set up Grafana dashboards

---

## Low Priority

### Add Automated Tests

**Components to test:**
- Config server endpoints
- Dashboard routes
- MQTT message handling
- Camera certificate generation

### Implement Logging Rotation

**Current:**
Logs grow indefinitely

**Solution:**
- Configure logrotate for application logs
- Archive old logs
- Implement log retention policy

### Add Health Check Endpoint

**Solution:**
Add `/health` endpoint to dashboard that checks:
- EMQX connectivity
- Database accessibility
- Disk space
- Service status

---

## Documentation Improvements

### Add Developer Guide
- Local development setup
- Testing procedures
- Contribution guidelines

### Add API Documentation
- Config server endpoints
- Dashboard API routes
- MQTT topic structure

### Add Troubleshooting Flowcharts
- Visual debugging guides
- Common issue decision trees

---

## Notes

**Priority Guidelines:**
- **High Priority:** Security or stability issues that affect production
- **Medium Priority:** Performance or reliability improvements
- **Low Priority:** Nice-to-have features and enhancements

**Before Making Changes:**
- Test thoroughly on development/staging environment
- Document changes in deployment guide
- Update requirements.txt
- Commit with clear descriptions
