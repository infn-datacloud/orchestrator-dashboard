# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Main module for running the Flask application.

This module initializes the Flask application using the `create_app` function from the `app` module.
The application is then run with the specified host and port when the script is executed directly.
"""
from app import create_app, redis_listener
from app.lib.pycharm_flask_debug_patch import restart_with_reloader_patch
import threading

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)


@app.before_request
def start_redis_listener():
    app.before_request_funcs[None].remove(start_redis_listener)
    thread = threading.Thread(target=redis_listener, args=(app.config.get("REDIS_URL"),), daemon=True)
    thread.start()
    app.logger.info(f"Redis listener thread started")


@app.after_request
def add_security_headers(response):
    # Force HTTPS
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    # Control referrer info
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"

    # Control permissions
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # Control cross-origin resource policy
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    
    # Control what resources can load
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' data: blob: https:; "
        
        # JS — local + CDNs
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdnjs.cloudflare.com "
        "https://cdn.jsdelivr.net "
        "https://use.fontawesome.com "
        "https://ajax.googleapis.com "
        "https://fonts.googleapis.com "
        "https://fonts.gstatic.com; "
        
        # CSS — local + CDNs + inline styles
        "style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com "
        "https://use.fontawesome.com "
        "https://cdn.jsdelivr.net "
        "https://cdnjs.cloudflare.com; "
        
        # Fonts — local + Google Fonts + FontAwesome
        "font-src 'self' data: https://fonts.gstatic.com https://use.fontawesome.com; "
        
        # Images — local, inline (base64), HTTPS favicons, etc.
        "img-src 'self' data: blob: https:; "
        
        # AJAX, WebSocket, APIs
        "connect-src 'self' https:; "
        
        # iframes or embeds (e.g., cookie consent popups)
        "frame-src 'self' https:; "
    )

    return response
