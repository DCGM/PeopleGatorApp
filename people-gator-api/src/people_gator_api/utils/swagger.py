"""Swagger presentation hooks; browser authentication stays in the frontend."""
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse


def swagger_html(*, openapi_url: str, title: str) -> HTMLResponse:
    response = get_swagger_ui_html(openapi_url=openapi_url, title=title)
    html = response.body.decode()
    initializer = "const ui = SwaggerUIBundle({"
    if initializer not in html:
        raise RuntimeError("Swagger HTML initializer changed; update the session hooks")
    html = html.replace(initializer, """const ui = window.ui = SwaggerUIBundle({
        requestInterceptor: (request) => window.peopleGatorDocsAuth
            ? window.peopleGatorDocsAuth.intercept(request) : request,
        onComplete: () => {
            window.peopleGatorDocsReady = true;
            window.dispatchEvent(new Event('peoplegator:docs-ready'));
        },""", 1)
    html = html.replace("</body>", '<script type="module" src="/swagger-auth.js"></script>\n</body>', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})
