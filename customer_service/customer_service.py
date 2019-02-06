import atexit
import json
import os
import uuid

from redis import StrictRedis
from flask import request
from flask import Flask

from lib.event_store import Event, EventStore


class Customer(object):
    """
    Customer Entity class.
    """

    def __init__(self, _name, _email):
        self.id = str(uuid.uuid4())
        self.name = _name
        self.email = _email


app = Flask(__name__)
redis = StrictRedis(decode_responses=True, host='redis')
store = EventStore(redis)

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    store.subscribe_to_entity_events('customer')
    atexit.register(store.unsubscribe_from_entity_events, 'customer')


@app.route('/customers', methods=['GET'])
@app.route('/customer/<customer_id>', methods=['GET'])
def get(customer_id=None):

    if customer_id:
        customer = store.find_one('customer', customer_id)
        if not customer:
            raise ValueError("could not find customer")

        return json.dumps(customer) if customer else json.dumps(False)
    else:
        return json.dumps([item for item in store.find_all('customer').values()])


@app.route('/customer', methods=['POST'])
@app.route('/customers', methods=['POST'])
def post():

    values = request.get_json()
    if not isinstance(values, list):
        values = [values]

    customer_ids = []
    for value in values:
        try:
            new_customer = Customer(value['name'], value['email'])
        except KeyError:
            raise ValueError("missing mandatory parameter 'name' and/or 'email'")

        # trigger event
        store.publish(Event('customer', 'created', **new_customer.__dict__))

        customer_ids.append(new_customer.id)

    return json.dumps(customer_ids)


@app.route('/customer/<customer_id>', methods=['PUT'])
def put(customer_id):

    value = request.get_json()
    try:
        customer = Customer(value['name'], value['email'])
    except KeyError:
        raise ValueError("missing mandatory parameter 'name' and/or 'email'")

    customer.id = customer_id

    # trigger event
    store.publish(Event('customer', 'updated', **customer.__dict__))

    return json.dumps(True)


@app.route('/customer/<customer_id>', methods=['DELETE'])
def delete(customer_id):

    customer = store.find_one('customer', customer_id)
    if customer:

        # trigger event
        store.publish(Event('customer', 'deleted', **customer))

        return json.dumps(True)
    else:
        raise ValueError("could not find customer")
