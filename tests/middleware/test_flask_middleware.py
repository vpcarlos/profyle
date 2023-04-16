import os

from flask import Flask

from profyle import ProfyleFlaskMiddleware


app = Flask("flask_test", root_path=os.path.dirname(__file__))
app.config.update(
    TESTING=True,
    SECRET_KEY="test key",
)

app.wsgi_app = ProfyleFlaskMiddleware(app.wsgi_app, pattern='*test*')


@app.route('/test')
def index():
    return 'Test'


def test_profyle_middleware():
    app.test_client().get('/test')
