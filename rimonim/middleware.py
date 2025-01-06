class DynamicSiteURLMiddleware:
    """
    Middleware to dynamically set the SITE_URL based on the current request's host and scheme.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set site_url dynamically based on request host and scheme
        request.site_url = f"{request.scheme}://{request.get_host()}"
        response = self.get_response(request)
        return response