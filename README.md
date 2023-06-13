## A Thing for FastAPI
#### Chatbot Using Dictionary Responses
##### Pre-requisites: 
...
*It is recommended to use a virtual environment*
```
# To create a python virtual environment
python -m virtualenv ./path/to/your/environment/

# Navigate to your virtual environment directory
cd ./path/to/your/environment/

# Start your virtual environment
source ./bin/activate

# To de-activate
deactivate
```
```
python -m pip install fastapi
python -m pip install uvicorn[standard]
```

 *To start using the chatbot use the following command*
```
uvicorn main:app --port 9190 --reload
```
```
--port: <can have any value>
--reload: server changes if the code changes [only for dev environment]
```
