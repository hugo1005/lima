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
    time: 0,
    tape: [],
    limitBooks: {},
    marketBooks: {},
    traders: [],
    // risk: {},
    // pnl: {}
}

const getters = {
    displayTape: state => state.tape,
    displayLimitBook: state => ticker => state.limitBooks[ticker],
    displayMarketBook: state => ticker => state.marketBooks[ticker],
    getTickers: state =>  Object.keys(state.limitBooks),
    getTraders: state => state.traders,
    displayLimitBooks: function(state, getters) {
      return getters.getTickers.map(ticker => getters.displayLimitBook(ticker))
    },
    displayMarketBooks: function(state, getters) {
      return getters.getTickers.map(ticker => getters.displayMarketBook(ticker))
    },
    // getRisk: state => state.risk,
    // getPnL: state => state.pnl
}

const mutations = {
    UPDATE_MARKET_BOOK(state, payload) {
      state.marketBooks = {...state.marketBooks, ...payload}
    },
    UPDATE_LIMIT_BOOK(state, payload) {
      // Correctly format halfbooks for display in book format
      for(let ticker of Object.keys(payload)) {
        payload[ticker].bid_book = fmt_halfbook(payload[ticker].bid_book, 'bid')
        payload[ticker].ask_book = fmt_halfbook(payload[ticker].ask_book, 'ask')
      }

      state.limitBooks = {...state.limitBooks, ...payload}
    },
    UPDATE_BOOK(state, payload) {
      state.books = {...state.books, ...payload}
    },
    UPDATE_TAPE(state, payload) {
      let payloadFmted = payload.map(transaction => {
        transaction.timestampRounded = round(transaction.timestamp, 3)
        return transaction
      })

      state.tape = state.tape.concat(payloadFmted)
    },
    UPDATE_TRADERS(state, payload) {
      state.traders = payload
    },
    UPDATE_TIME(state, payload) {
      state.time = payload
    },
    // UPDATE_RISK(state, payload) {
    //   state.risk = risk
    // },
    // UPDATE_PNL(state, payload) {
    //   state.pnl[payload.ticker] = payload
    // },
    SET_CONNECTION(state, payload) {
      state.connected = payload
    },
    SET_ERROR(state, payload) {
      state.error = payload
    }
}

const actions = {
    updateLimitBook({ commit }, payload) {
      commit('UPDATE_LIMIT_BOOK', payload)
    },
    updateMarketBook({ commit }, payload) {
      commit('UPDATE_MARKET_BOOK', payload)
    },
    updateTape({ commit }, payload) {
      commit('UPDATE_TAPE', payload)
    },
    updateTraders({ commit }, payload) {
      commit('UPDATE_TRADERS', payload)
    },
    updateTime({ commit }, payload) {
      commit('UPDATE_TIME', payload)
    },
    // updateRisk({ commit }, payload) {
    //   commit('UPDATE_RISK', payload)
    // },
    // updatePnL({ commit }, payload) {
    //   commit('UPDATE_PNL', payload)
    // },
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