import {InvForm} from './create_inv'
// import {App} from './prod_components'
import ReactDOM from 'react-dom';
import React from 'react';
import {Route, Router, Link, browserHistory} from 'react-router'

var router = <Router history={browserHistory}>
    <Route name="create_inv" path='/inv' component={InvForm} />
</Router>;
//    <Route name="transfer" path='/transfer' component={App} />
ReactDOM.render(router, document.getElementById('content'));
