from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    var = "Hello from people-gator-api!"
    for i, c in enumerate(var):
        print(f"{i}: {c}")
        if i > 2:
            break
        else:
            print("Continuing...")
    return {"message": var}
