def post_worker_init(worker):
    """Runs in each worker after the app is loaded and before it accepts requests."""
    from grantlens_api.warmup import warm_up

    warm_up(worker.wsgi)
