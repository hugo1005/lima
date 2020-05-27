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
    exchangeOpenTime: -1,
    connected: false,
    error: null,
    time: 0,
    tape: [],
    limitBooks: {},
    marketBooks: {},
    traders: [],
    // Tick data will be irregular intervals and at maximum possible resolution timestamp
    tickData: [], // {[{ticker:, Timestamp:, BestBid:, BestAsk:, BuyerInitiatedVol:, SellerInitiatedVol:}]}
    resolution: 5,
    groupedTicks: {}, // {ticker:{bucketedTimestamp:[{ timestamp:, bestBid:, bestAsk:, buyerInitiatedVol:, bellerInitiatedVol:}]}
    ohlc: [], // {[{ticker:, timestamp:, o:, h:, l:, c:, buyerInitiatedVol:, bellerInitiatedVol:, vol:}]}
    securityParams: {}, // {ticker:{resolution:}}
    // risk: {},
    // pnl: {}
}

const getters = {
    displayTape: state => state.tape,
    displayLimitBook: state => ticker => state.limitBooks[ticker],
    displayMarketBook: state => ticker => state.marketBooks[ticker],
    getTickers: state =>  Object.keys(state.limitBooks),
    getTickData: state => ticker => state.tickData.filter(tick => tick.ticker == ticker),
    getTraders: state => state.traders,
    getSecurityParams: state => ticker => state.securityParams[ticker],
    getTickerOHLC: state => ticker => state.ohlc.filter(candle => candle.ticker == ticker),
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
    // UPDATE_BOOK(state, payload) {
    //   state.books = {...state.books, ...payload}
    // },
    UPDATE_TAPE(state, payload) {
      let payloadFmted = payload.map(transaction => {
        transaction.timestampRounded = round(transaction.timestamp, 3)
        return transaction
      })
      
      state.tape = state.tape.concat(payloadFmted)
    },
    UPDATE_TICK_DATA(state, payload) {
      let resolution = state.resolution

      for(let transaction of payload) {
        let ticker = transaction.ticker
        let qty = transaction.qty
        let action = transaction.action
        let book = state.limitBooks[ticker]
        let bestBid = book.bid_book.length > 0? book.bid_book[0].price: transaction.price
        let bestAsk = book.ask_book.length > 0? book.ask_book[0].price: transaction.price
        
        let tick = {
          'ticker': ticker,
          'timestamp': transaction.timestamp, 
          'bestBid': bestBid, 
          'bestAsk': bestAsk, 
          'buyerInitiatedVol': action == 'BUY'? qty: 0,  // Action in direction of liquidity taker
          'sellerInitiatedVol': action == 'SELL'? qty: 0,
        }

        // Stores the raw tick
        state.tickData.push(tick)
        
        // Note this intermediary state is currently unused
        // But may be useful in the future
        // Store the bucketed tick
        let bucketedTimestamp = Math.floor(tick.timestamp / resolution) * resolution
        state.groupedTicks[ticker] = state.groupedTicks[ticker] || {}
        state.groupedTicks[ticker][bucketedTimestamp] = state.groupedTicks[ticker][bucketedTimestamp] || []
        state.groupedTicks[ticker][bucketedTimestamp].push(tick)

        // Update OHLC
        // This is slightly more efficient than the previous implementation
        // As we only ever need to update the latest candle
        let idx = state.ohlc.findIndex(candle => candle.ticker == ticker && candle.timestamp == bucketedTimestamp)
        
        let timestampTickData = state.groupedTicks[ticker][bucketedTimestamp]
        let firstTick = timestampTickData[0]
        let lastTick = timestampTickData[timestampTickData.length - 1]
        let bestBids = timestampTickData.map(tick => tick.bestBid)
        let bestAsks = timestampTickData.map(tick => tick.bestAsk)
        let minBid = Math.min(...bestBids)
        let maxBid = Math.max(...bestBids)
        let minAsk = Math.min(...bestAsks)
        let maxAsk = Math.max(...bestAsks)

        let bidVol = timestampTickData.reduce((total, tick) => total + tick.buyerInitiatedVol, 0)
        let askVol = timestampTickData.reduce((total, tick) => total + tick.sellerInitiatedVol, 0)
        
        let roundPrice = price => round(price, state.securityParams[ticker].resolution)

        let candle = {
            'ticker': ticker,
            'timestamp': bucketedTimestamp,
            'o': roundPrice((firstTick.bestBid + firstTick.bestAsk)/2),
            'h': roundPrice((maxBid + maxAsk)/2), // To obtain less biased estimates we avg
            'l': roundPrice((minBid + minAsk)/2),
            'c': roundPrice((lastTick.bestBid + lastTick.bestAsk)/2),
            'buyerInitiatedVol': bidVol,
            'sellerInitiatedVol': askVol,
            'vol': bidVol + askVol,
        }

        if(idx >= 0) {
          state.ohlc.splice(idx, 1, candle)
        } else {
          state.ohlc.push(candle)
        }

      }
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
    },
    SET_EXCHANGE_OPEN_TIME(state, payload) {
      state.exchangeOpenTime = payload
    },
    CONFIGURE_SECUIRTY_PARAMETERS(state, payload) {
      let tickers = Object.keys(payload)
      
      // CONFIGURE TICK DATA
      for(let ticker of tickers) {
        state.tickData[ticker] = []
      }

      // CONFIGURE PARAMATERS
      state.securityParams = tickers.reduce((params, ticker) => {
        params[ticker] = {resolution: payload[ticker].resolution}
        return params
      }, {})
    }
}

const actions = {
    configBackend({ commit }, payload) {
      // There is more information in this payload but we don't need it for now
      commit('SET_EXCHANGE_OPEN_TIME', payload.exchange_open_time)
      commit('CONFIGURE_SECUIRTY_PARAMETERS', payload.exchange.securities)
    },
    updateLimitBook({ commit }, payload) {
      commit('UPDATE_LIMIT_BOOK', payload)
    },
    updateMarketBook({ commit }, payload) {
      commit('UPDATE_MARKET_BOOK', payload)
    },
    updateTape({ commit }, payload) {
      commit('UPDATE_TAPE', payload)
      commit('UPDATE_TICK_DATA', payload)
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