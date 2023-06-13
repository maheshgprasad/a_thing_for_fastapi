from fastapi import FastAPI

import chatbot as cb

app = FastAPI()


@app.get("/bot/{query}")
async def mijoo(query: str):
  answer=cb.get_response(query)
  return[answer]

