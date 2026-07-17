from fastapi import Body, FastAPI, Response, status, HTTPException
from pydantic import BaseModel
from typing import Optional
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import time

app = FastAPI()
 

class Post(BaseModel):
    title: str
    content: str
    published: Optional[bool] = None
    rating: Optional[int] = None

    # Optional[bool] just says "this field accepts bool or None as a value"
    # = None is what actually makes it optional to include in the payload



my_posts = [{"title": "Top 10 MMA fighters of all time", "content": "Here are the top 5 UFC fighters of all time", "id": 1},
            {"title": "Top 10 Buildings of all time", "content": "Here are the top 5 Buildings of all time", "id": 2}]


while True:
    try:
        conn = psycopg2.connect(host='localhost', database='fastapi', user='postgres', password='Dion1355', cursor_factory=RealDictCursor)
        # cursor_factory=RealDictCursor: this gives the column name along with the values when you query data. 
        cursor = conn.cursor()
        print("database works!!!!")
        break
    except Exception as errors:
        print(f"connecting to database failed: {errors}")
        time.sleep(2)


def find_post(id):
    for post in my_posts:
        if post['id'] == id:
            return post


def find_idx(id):
    for idx, post in enumerate(my_posts):
        if post['id'] == id:
            return idx


"""
    Path operation / route.
    The decorator below, turns the funciton into a path operation so person trying to use the api can hit the endpoint. 

    decorator structure: @instace_of_fastapi(i.e. check above) + http method the user should 
    use to get to the function + root path(i.e the path the user has to write after writing the 
    domain name in the user, e.g if the () has '/login' then the user would have to write the 
    domain name + /login in order to make the http method request(i.e. in this case the get request 
    which would then run the funciton below the dec)).
"""
# The decorator makes the funciton go: "whenever someone sends this http method(i.e. get request), run the login_user function".
@app.get("/")
def login_user():
    return {"message": "Hello World"}
#if htis function logs in a user, the return is the output then gets sent back to whoever made the get request, in this case the user. 
#In the above funciton we are returning a dictionary, fastapi automatically converts this to a json. 



@app.get("/posts")
def login_user():
    return {"data": my_posts}


"""
    payload: dict = Body(...)
    #  ^       ^       ^
    #  |       |       |
    #  |       |       look in the request body, and it's required
    #  |       expect a dictionary
    #  store it in this variable

"""

# One way of accepting values from get request. 

# @app.post("/createpost")
# def create_post(payload: dict = Body(...)):
#     return {f"title: {payload['title']}, content: {payload['content']}"}

# More optimal way - use pydantic.

# we set the status_code in the decorator to set the default status code for this path operation. 
@app.post("/createpost", status_code=status.HTTP_201_CREATED)
def create_post(post: Post):
    post_dict = post.model_dump()
    post_dict['id'] = random.randrange(1, 1e6)
    my_posts.append(post_dict)
    return {"data": f"title: {post_dict['title']}, content: {post_dict['content']}, id:{ post_dict['id']}"}


# Here the id: int, by adding int, fastapi validates the type of the id value, if it isn't int then fastapi will throw an error. 
@app.get("/posts/{id}")
def get_post(id: int):
    post = find_post(id)
    if not post: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"The post with id: {id} not found")
    
    return {"post": post}


# when we send a 204, we don't/can't send any data back, hence use the response object in the return or its fine to also send None. 
@app.delete("/posts/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(id: int):
    idx = find_idx(id)
    if idx == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id: {id} not found.")
    my_posts.pop(idx)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/posts/{id}")
def update_posts(id: int, post: Post):
    idx = find_idx(id)
    if idx is None:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id: {id} is not found.")
    
    post = post.dict()
    for key in post:
        my_posts[idx][key] = post[key]
    return {"message": "updated post"}
    