import os


bind = f"0.0.0.0:{os.getenv('PORT', os.getenv('FLASK_PORT', '8080'))}"
workers = int(os.getenv('WEB_CONCURRENCY', '2'))
threads = int(os.getenv('WEB_THREADS', '4'))
timeout = int(os.getenv('WEB_TIMEOUT', '120'))
accesslog = '-'
errorlog = '-'
