import React from 'react';
import ReactDOM from 'react-dom';
import LinkedStateMixin from 'react-addons-linked-state-mixin';
import SkyLight from './skylight';
import twoDecimalPlace from './view_account';
import {NewProduct} from './importation_edit_prod';

const API = '/import';

// providor_name, upi's
//
function selectInput(ref) {
    var dom = ReactDOM.findDOMNode(ref);
    dom.focus();
    dom.select();
}
function testEnter(ref, event) {
    if (event.key == 'Enter') {
        selectInput(ref);
    }
}


function getItemValue(item) {
    return Math.round(item.price_rmb * item.quantity * 100) / 100;
}

// This edits an PurchaseItem, usually shown inside of a skyline
var EditItem = React.createClass({
    mixins: [LinkedStateMixin],
    getInitialState() {
        return { prod_detail: {name_zh: ''}, box: '', price_rmb: 0, quantity: 0};
    },
    saveEdited() {
        var providor_zh = this.state.prod_detail.providor_zh;
        var data = {
            box: this.state.box,
            price_rmb: this.state.price_rmb,
            quantity: this.state.quantity,
            color: this.state.color,
        };
        this.props.onEditedItem(this.state.itemPosition, data);
    },
    render() {
        return <table className="table"><tbody>
            <tr>
                <td>{"产品:"} </td>
                <td>{this.state.prod_detail.name_zh} ({this.state.prod_detail.unit})</td>
            </tr>
            <tr>
                <td>{"箱数:"} </td>
                <td><input valueLink={this.linkState('box')} /></td>
            </tr>
            <tr>
                <td>{"价格:"} </td>
                <td><input valueLink={this.linkState('price_rmb')} /></td>
            </tr>
            <tr>
                <td>{"数量:"} </td>
                <td><input valueLink={this.linkState('quantity')} /></td>
            </tr>
            <tr>
                <td>{"颜色:"} </td>
                <td><input valueLink={this.linkState('color')} /></td>
            </tr>
            <tr>
                <td>{"一共:"} </td>
                <td>{getItemValue(this.state)}</td>
            </tr>
            <tr>
                <td><button onClick={this.saveEdited}>{"确定"}</button> </td>
                <td></td>
            </tr>
            </tbody></table>;
    }
});


// List of PurchaseItem (usually in lower right panel)
class ItemList extends React.Component {
    constructor(props) {
        super(props);
        this.onEditedItem = this.onEditedItem.bind(this);
    }
    onDeleteItem(item, event) {
        this.props.deleteItem(item, event.target.value);
    }
    editItem(item, itemPosition) {
        console.log(item); 
        var state = Object.assign({}, item.item);
        state['prod_detail'] = item.prod_detail;
        state['itemPosition'] = itemPosition;
        this.refs.createItem.show();
        this.refs.createItemBox.setState(state);
    }
    onEditedItem(itemPosition, data) {
        var item = this.props.items[itemPosition];
        this.props.onEditedItem(item, data);
        this.refs.createItem.hide();
    }
    render() {
        var rows = this.props.items.map((item, i) => {
            var moreStyle = ('_deleted' in item.item && item.item._deleted) ? {'text-decoration': 'line-through'} : {};
            if (('_new' in item.item && item.item._new) ||
                ('_edited' in item.item && item.item._edited)) {
                moreStyle['background-color'] = 'yellow';
            }
            var unit = item.prod_detail.unit in this.props.units ? this.props.units[item.prod_detail.unit].name_zh 
                                                                 : item.prod_detail.unit;
            return <tr style={moreStyle}>
                <td className="number">{item.item.box || ''}</td>
                <td>{item.prod_detail.name_zh}({unit}) {item.item.color} </td>
                <td className="number">{Number(item.item.quantity)}</td>
                <td className="number">{Number(item.item.price_rmb).toFixed(4)}</td>
                <td className="number">
                    {(Math.round(item.item.price_rmb*  item.item.quantity * 100) / 100).toFixed(2)}
                </td>
                <td><input type="checkbox"
                           checked={item.item._deleted}
                           onChange={this.onDeleteItem.bind(this, item)} /></td>
                <td><button type="button" onClick={this.editItem.bind(this, item, i)}>{'更改'}</button></td>
            </tr>;
       });
        return <div>
                <SkyLight hiddenOnOverlayClicked ref="createItem" title={"更改"}>
                    <EditItem ref="createItemBox" onEditedItem={this.onEditedItem} />
                </SkyLight>
                <table className="table">
                <thead>
                    <tr>
                        <th className="number">{"箱数"}</th>
                        <th>{"产品"}</th>
                        <th className="number">{"数量"}</th>
                        <th className="number">{"价格"}</th>
                        <th className="number">{"一共"}</th>
                        <th>{'删除？'}</th>
                        <th>{''}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
        </table>
        </div>;
    }
}

// props:
//  meta = Purchase
//  items = list of PurchaseItems
// state:
//  meta = Purchase,
//  items_by_providor = dict of providor -> list of items
//  providors = list of providors
export class EditPurchase extends React.Component {
    constructor(props) {
        super(props);
        this.setProvidorBox = this.setProvidorBox.bind(this);
        this.onNewItem = this.onNewItem.bind(this);
        this.onDeleteItem = this.onDeleteItem.bind(this);
        this.onEditedItem = this.onEditedItem.bind(this);
        this.onSelectProvidorVal = this.onSelectProvidorVal.bind(this);
        this.onNewProvidor = this.onNewProvidor.bind(this);
        this.savePurchase = this.savePurchase.bind(this);
        this.setStatusReady = this.setStatusReady.bind(this);
        this.showAddNewProduct = this.showAddNewProduct.bind(this);
        this.onNewProduct = this.onNewProduct.bind(this);
        this.changeMeta = this.changeMeta.bind(this);
        this.getAllProducts();
        this.getFullInv(this.props.params.uid);
        this.getAllUnits();
        this.state = {
            all_providors: [],
            providors: [],
            providors_data: {},
            allprod:{},
            items_by: {},
            currentProvidor: null,
            meta: {},
            units: {},
            declared: [],
        };
    }
    onSelectProvidorVal(prov) {
        this.setState({currentProvidor: prov});
        this.refs.productSelector.focusCant();
    }
    onNewProvidor(prov) {
        this.state.providors.push(prov);
        this.state.items_by[prov] = [];
        this.state.providors_data[prov] = {
            box: 0, total: 0};
        this.setState({
            providors: this.state.providors,
            items_by: this.state.items_by,
            providors_data: this.state.providors_data,
        });
    }
    getAllUnits() {
        $.ajax({
            url: API + '/unit',
            success: (result) => {
                result = JSON.parse(result);
                this.setState({'units': result});
            }
        });
    }
    getFullInv(uid) {
        $.ajax({
            url: API + '/purchase_full/' + uid,
            success: (result) => {
                if (typeof result === 'string') {
                    result = JSON.parse(result);
                }
                var providors = [];
                var items_by = {};
                var providors_data = {};
                for (var i in result.items) {
                    var item = result.items[i];
                    var prov = item.prod_detail.providor_zh;
                    if (!(prov in items_by)) {
                        items_by[prov] = [];
                        providors_data[prov] = {};
                        providors_data[prov].box = 0;
                        providors_data[prov].total = 0;
                        providors.push(prov);
                    }
                    items_by[prov].push(item);
                    providors_data[prov].box += Number(item.item.box) || 0;
                    providors_data[prov].total += getItemValue(item.item);
                }
                this.setState({
                    items_by: items_by,
                    providors: providors,
                    providors_data: providors_data,
                    meta: result.meta,
                });
            }
        });
    }
    getAllProducts() {
        $.ajax({
            url: API + '/universal_prod_with_declared',
            success: (result) => {
                if (typeof result === 'string') {
                    result = JSON.parse(result);
                }
                var allprod = {};
                for (var x in result.prod) {
                    var item = result.prod[x];
                    if (!(item.providor_zh in allprod)) {
                        allprod[item.providor_zh] = [];
                    }
                    allprod[item.providor_zh].push(item);
                }
                var providors = Object.keys(allprod);
                result.declared.sort((a, b) => a.display_name.localeCompare(b.display_name));
                providors.sort((a, b) => a.localeCompare(b, [ "zh-CN-u-co-pinyin" ]));
                for (var i in providors) {
                    allprod[providors[i]].sort(
                            (a, b) => a.name_zh.localeCompare(b.name_zh,[ "zh-CN-u-co-pinyin" ]));
                }
                this.setState({
                    all_providors: providors,
                    allprod: allprod,
                    declared: result.declared,
                });
            }
        });
    }
    onNewItem(item) {
        this.state.items_by[item.prod_detail.providor_zh].push(item);
        this.state.providors_data[item.prod_detail.providor_zh].total += getItemValue(item.item);
        this.setState({items_by: this.state.items_by});
        var dom = ReactDOM.findDOMNode(this.refs.itemListContainer);
        dom.scrollTop = dom.scrollHeight + 50;
    }
    onDeleteItem(item, value) {
        if ('_deleted' in item.item) {
            item.item._deleted = !item.item._deleted;
        } else {
            item.item._deleted = true;
        }
        this.setState({items_by: this.state.items_by});
    }
    onEditedItem(item, content) {
        Object.assign(item.item, content);
        item.item._edited = true;
        this.setState({items_by: this.state.items_by});
    }
    setProvidorBox(event) {
        if (this.state.currentProvidor == null) {
            return;
        }
        var value = Number(event.target.value);
        this.state.providors_data[this.state.currentProvidor].box = value;
        this.state.providors_data[this.state.currentProvidor]._edited = true;
        this.setState({providors_data: this.state.providors_data});
    }
    savePurchase() {
        var payload = {
            meta: this.state.meta,
            create_items: [],
            delete_items: [],
            edit_items: [],
        };

        for (var prov in this.state.items_by) {
            var prov_data = this.state.providors_data[prov];
            var modify_box = '_edited' in prov_data && prov_data._edited;
            var cant_sum = 0;
            var curbox = 0;
            if (modify_box) {
                for (var j in this.state.items_by[prov]) {
                    var item = this.state.items_by[prov][j];
                    var box = Number(item.item.box || 0);
                    if (box == 0) {
                        cant_sum += Number(item.item.quantity);
                    }
                    curbox += box;
                }
            }
            for (var j in this.state.items_by[prov]) {
                var item = this.state.items_by[prov][j];
                var deleted = '_deleted' in item.item && item.item._deleted;
                var isNew = '_new' in item.item && item.item._new;
                var edited = '_edited' in item.item && item.item._edited;
                if (modify_box && Number(item.item.box || 0) == 0) {
                    item.item.box = (Number(prov_data.box) - curbox) * item.item.quantity / cant_sum;
                    edited = true;
                }
                if (isNew && deleted) {
                    // do nothing
                    continue;
                }
                if (deleted) {
                    // regardless of if edited 
                    payload.delete_items.push(item.item);
                    continue;
                }
                if (isNew) {
                    // regardless of edited
                    payload.create_items.push(item.item);
                    continue
                }
                if (edited) {
                    // not new and not deleted
                    payload.edit_items.push(item.item);
                }
            }
        }
        console.log(payload);
        $.ajax({
            url: API + '/purchase_full/' + this.props.params.uid,
            data: JSON.stringify(payload),
            method: 'PUT',
            success: (x) => {
                alert('保存成功');
                this.getFullInv(this.props.params.uid);
            }
        });
    }
    setStatusReady() {
        this.state.meta.status = 'READY';
        this.savePurchase();
    }
    showAddNewProduct() {
        this.refs.addNewProduct.show();
        this.refs.addNewProductBox.setState({providor_zh: this.state.currentProvidor});
    }
    onNewProduct(product) {
        if (!(product.providor_zh in this.state.allprod)) {
            this.state.allprod[product.providor_zh] = [];
            this.state.all_providors.push(product.providor_zh);
        }
        this.state.allprod[product.providor_zh].push(product);
        this.setState({allprod: this.state.allprod, all_providors: this.state.all_providors});
        this.refs.addNewProduct.hide();
    }
    changeMeta(event) {
        this.state.meta[event.target.name] = event.target.value;
        this.setState({meta: this.state.meta});
    }
    render() {
        var currentItems = [];
        var currentAllProd = [];
        var currentData = {box: 0, total: 0};
        if (this.state.currentProvidor) {
            currentItems = this.state.items_by[this.state.currentProvidor];
            currentAllProd = this.state.allprod[this.state.currentProvidor];
            currentData = this.state.providors_data[this.state.currentProvidor];
        }
        var total_rmb = 0;
        var total_box = 0;
        for (var x in this.state.items_by) {
            for (var i in this.state.items_by[x]) {
                var item = this.state.items_by[x][i];
                total_rmb += getItemValue(item.item);
                total_box += Number(item.item.box || 0);
            }
        }
        const addNewProdStyle = {
            height: '70vh',
            marginTop: '-200px',
            overflowY: 'scroll',
        }

        return <div className="container" style={{height: '100%'}}>
            <SkyLight hiddenOnOverlayClicked dialogStyles={addNewProdStyle} ref="addNewProduct" title={"新产品"}>
                <NewProduct ref="addNewProductBox" 
                    units={this.state.units} onNewProduct={this.onNewProduct} 
                    declared={this.state.declared} />
            </SkyLight>
        <div className="row">
            <div className="col-sm-4">
                <p><label>{'货柜日期'}</label>
                <input name="timestamp" value={this.state.meta.timestamp} onChange={this.changeMeta}/></p>
                <label>{'上次更改'}</label>
                {this.state.meta.last_edit_timestamp}
            </div>
            <div className="col-sm-4">
                <p><label>{'订单毛重'}</label>
                <input name="total_gross_weight_kg" 
                       onChange={this.changeMeta} 
                       value={this.state.meta.total_gross_weight_kg}/></p>
                <label>{'订单箱数'}</label>
                <input name="total_box" onChange={this.changeMeta} value={this.state.meta.total_box} />
            </div>
            <div className="col-sm-4">
                <p><label>{'总价 '}</label>{total_rmb.toFixed(2)}
                       <label>{' 箱数 '}</label>{total_box.toFixed(3)}</p>
                <button onClick={this.showAddNewProduct}>{'添加新产品'}</button>
                {this.state.meta.status != 'CUSTOM' ?
                [<button className="btn btn-sm btn-warning" onClick={this.savePurchase}>{'保存'}</button>,
                <button className="btn btn-sm btn-danger" onClick={this.setStatusReady}>{'完成'}</button>] 
                    :''}

            </div>
        </div>
        <div className="row" style={{height: '90%'}}>
            <div className="col-sm-4" >
                <ProvidorSelector all_providors={this.state.all_providors}
                                  currentProvidor={this.state.currentProvidor}
                                  providors={this.state.providors}
                                  providors_data={this.state.providors_data}
                                  onNewProvidor={this.onNewProvidor}
                                  onSelectProvidor={this.onSelectProvidorVal}
                                  />
            </div>
            <div className="col-sm-8">
                <div className="row">
                    {this.state.currentProvidor}
                    <span style={{marginLeft: '200px'}}>{'箱数'}
                        <input ref='totalBox' value={currentData.box || ''}
                        onChange={this.setProvidorBox} /></span>
                    <span style={{marginLeft: '10px'}}>{'钱数'}
                        {currentData.total || ''}</span>
                </div>
                <div className="row">
                    <ProductSelector ref="productSelector" prods={currentAllProd}
                        units={this.state.units}
                        onNewItem={this.onNewItem}/>
                </div>
                <div ref="itemListContainer" style={{height: '75vh',
                    'overflowY': 'scroll'}}>
                    <ItemList items={currentItems} deleteItem={this.onDeleteItem} 
                        units={this.state.units}
                        onEditedItem={this.onEditedItem}/>
                </div>
            </div>
        </div>
        </div>;
    }
}

// all_providors
// providors
// providor_data
// onSelectProvidor
// onNewProvidor
class ProvidorSelector extends React.Component {
    constructor(props) {
        super(props);
        this.addProvidor = this.addProvidor.bind(this);
    }
    addProvidor(event) {
        var prov = this.refs.newProvidor.value;
        var index = this.props.providors.indexOf(prov);
        var dom = ReactDOM.findDOMNode(this.refs.allProvidorList);
        if (index != -1) {
            console.log(prov, 'exists');
            dom.scrollTop = 33 * index + 50;
        } else {
            this.props.onNewProvidor(prov);
            dom.scrollTop = dom.scrollHeight + 50;
        }
        this.props.onSelectProvidor(prov);
    }
    render() {
        return <div>
            <div>
                <select ref="newProvidor">
                    {this.props.all_providors.map((x) =>
                            <option key={x} value={x}>{x}</option>)}
                </select>
                <button onClick={this.addProvidor}>{'添加'}</button>
            </div>
            <div ref='allProvidorList' id="allProvidorList" style={{height: '75vh',
                'overflowY': 'scroll'}}>
             <table className="table"><tbody>
                 {this.props.providors.map((prov, pos) => {
                    return <tr className='selectable'
                        ref={'providorList' + pos}
                        value={prov}
                        onClick={this.props.onSelectProvidor.bind(null, prov)}>
                     <td><input type="radio" readOnly
                            name="selected_providor" value={prov}
                            checked={this.props.currentProvidor==prov}
                        />
                     </td>
                     <td>{prov}</td>
                     <td className="number">
                        {Number(this.props.providors_data[prov].box).toFixed(3)}</td>
                     <td className="number">
                        {this.props.providors_data[prov].total.toFixed(2)}</td>
                     </tr>
                 })}
            </tbody></table>
            </div>
        </div>;
    }
}

class ProductSelector extends React.Component {
    constructor(props) {
        super(props);
        this.focusCant = this.focusCant.bind(this);
        this.focusPrice = this.focusPrice.bind(this);
        this.focusBox = this.focusBox.bind(this);
        this.addItem = this.addItem.bind(this);
        this.addItemOnKey = this.addItemOnKey.bind(this);
    }
    focusCant(event) {
        selectInput(this.refs.quantity);
    }
    focusBox(event) {
        testEnter(this.refs.box, event);
    }
    focusPrice(event) {
        testEnter(this.refs.price_rmb, event);
    }
    addItem(event) {
        if (!this.props.prods || this.props.prods.length == 0) {
            return;
        }
        var meta = {
            upi: this.refs.newProduct.value,
            quantity: this.refs.quantity.value,
            price_rmb: this.refs.price_rmb.value,
            box: this.refs.box.value,
            color: this.refs.color.value,
            _new: true,
        };
        var prod_detail = null;
        for (var i in this.props.prods) {
            if (this.props.prods[i].upi == meta.upi) {
                prod_detail = this.props.prods[i];
            }
        }
        this.props.onNewItem({
            item: meta,
            prod_detail: prod_detail
        });
    }
    addItemOnKey(event) {
        if (event.key == 'Enter') {
            this.addItem()
        }
    }
    render() {
        return <div>
            <select ref="newProduct" onChange={this.focusCant}>
            {this.props.prods.map((x) => {
                    var unit = x.unit in this.props.units ? this.props.units[x.unit].name_zh : x.unit;
                    return <option key={x.upi} value={x.upi}>
                        ({x.providor_item_id}){x.name_zh}({unit})</option>;
            })}
            </select>
            <input className="smallNum"
                ref="quantity" onKeyDown={this.focusPrice} placeholder={'数量'}/>
            <input className="smallNum"
                ref="price_rmb" onKeyDown={this.focusBox} placeholder={'价格'}/>
            <input className="smallNum" onKeyDown={this.addItemOnKey}
                ref="box" placeholder={'箱数'}/>
            <button onClick={this.addItem}>{'添加'}</button>
            <input className="smallNum"
                ref="color" placeholder={'颜色'}/>
        </div>;
    }
}
