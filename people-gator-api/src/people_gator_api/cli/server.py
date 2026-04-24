from people_gator_api.app import app
from people_gator_api.utils.settings import settings
import uvicorn

def server() -> None:
    uvicorn.run(
        "people_gator_api.app:app", 
        host=settings.host, 
        port=settings.port, 
        reload=settings.reload
    )

if __name__ == "__main__":
    server()
