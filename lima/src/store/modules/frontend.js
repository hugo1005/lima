import { round } from 'mathjs'

function fmt_halfbook(halfbook, side='bid') {
  /** 
   * Takes either this bid or ask side of a limit orderbook
   * and formats is to a list of orders sorted in price time priority
   * @param {Object} halfbook halfboook object of orders in json format as specified in shared.py
   * @param {String} side indicates which side of the book, either bid or ask
  */

  if (['bid','ask'].indexOf(side) == -1) throw `invalid book side specified: ${side}`
  
  let ascending = side == 'bid'? false: true
  let sorted_prices = Object.keys(halfbook).sort((a,b) => ascending ? a - b : b - a)
  let fmted_halfbook = [].concat.apply([], sorted_prices.map(price => halfbook[price]))

  return fmted_halfbook
}

const state = {
    connected: false,
    error: null,
    tid: null,
    traderOpenOrderKeys: [],
    traderCompletedOrders: [],
    traderFills: [],
    risk: {},
    pnl: [],
    pnlTickers: {},
    productData: [],
    products: new Set()
}

const getters = {
    getTID: state => state.tid,
    getTraderOpenOrderKeys: state => state.traderOpenOrderKeys,
    getTraderCompletedOrders: state => state.traderCompletedOrders,
    getTraderFills: state => state.traderFills,
    getProducts: state => state.products,
    getProduct: state => ticker => state.productData.filter(tick => tick.ticker == ticker),
    getRisk: state => state.risk,
    getPnL: state => state.pnl,
}

const mutations = {
    REGISTER_ORDER(state, payload) {
        state.traderOpenOrderKeys.push(payload)
    },
    DEREGISTER_ORDER(state, payload) {
        state.traderOpenOrderKeys = state.traderOpenOrderKeys.filter(orderKey => orderKey.order_id !== payload.order_id)
    },
    FILL_ORDER(state, payload) {
        state.traderFills.push(payload)
    },
    COMPLETE_ORDER(state, payload) {
        state.traderCompletedOrders.push(payload)
    },
    UPDATE_RISK(state, payload) {
      state.risk = payload
    },
    UPDATE_PNL(state, payload) {
      let ticker =  payload.ticker
    
      // Transformation done here for ease of display
      if (ticker in state.pnlTickers) {
        let idx = state.pnlTickers[ticker]
        state.pnl.splice(idx, 1, payload) // Done to ensure reactivity of getters!

      } else {
        state.pnlTickers[ticker] = state.pnl.length
        state.pnl.push(payload)
      }
      
    },
    UPDATE_PRODUCT(state, payload) {
      // Registers the product if necessary
      state.products.add(payload.ticker)
      // Updates the list of product data
      state.productData.push(payload)
    },
    SET_TID(state, payload) {
        state.tid = payload
    },
    SET_CONNECTION(state, payload) {
      state.connected = payload
    },
    SET_ERROR(state, payload) {
      state.error = payload
    }
}

const actions = {
    registerOrder({ commit }, payload) {
        commit('REGISTER_ORDER', payload)
    },
    fillOrder({ commit }, payload) {
        commit('FILL_ORDER', payload.transaction)
    },
    completeOrder({ commit }, payload) {
        commit('FILL_ORDER', payload.transaction)
        commit('DEREGISTER_ORDER', payload.order)
        commit('COMPLETE_ORDER', payload.order)
    },
    updateTID({ commit }, payload) {
        commit('SET_TID', payload)
    },
    updateRisk({ commit }, payload) {
        commit('UPDATE_RISK', payload)
    },
    updatePnL({ commit }, payload) { // Recieves pnl update for a single ticker
        commit('UPDATE_PNL', payload) 
    },
    updateProduct({ commit }, payload) {
      commit('UPDATE_PRODUCT', payload)
    },
    connectionOpened({ commit }) {
      commit('SET_CONNECTION', true)
    },
    connectionClosed({ commit }) {
      commit('SET_CONNECTION', false)
    },
    connectionError({ commit }, payload) {
      commit("SET_ERROR", payload)
    }
}

export default {
    namespaced: true,
    state,
    getters,
    actions,
    mutations
}