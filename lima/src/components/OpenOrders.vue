<template>
    <BaseCard title="Trader Orders" :hasStats='false'>
        <template #contentLeft>
            <CardTable 
            title="Open"
            :tableHeaders="contentHeaders"
            :itemKeys="openOrderContentKeys"
            :items='openOrdersAggregated'
            itemUniqueIdentifer='key'
            :cellHighlight='colorBuySell'
            :rowHighlight='canHighlightTransaction'
            ></CardTable>
        </template>

        <template #contentRight>
            <CardTable
            title="Completed"
            :tableHeaders="contentHeaders"
            :itemKeys="completedOrderContentKeys"
            :items='completedOrdersAggregated'
            itemUniqueIdentifer='key'
            accentColor = '#EC7F6C'
            accentBg = 'rgba(236, 127, 108, 0.3)'
            :cellHighlight='colorBuySell'
            :rowHighlight='canHighlightTransaction'
            ></CardTable>
        </template>
    </BaseCard>
</template>

<script>
import { mapGetters } from 'vuex'
import BaseCard from '../components/BaseCard.vue'
import CardTable from '../components/CardTable.vue'
import HighlightTable from '../mixins/HighlightTable'

function aggregate_order_qtys(ordersToAgg, tickers) {
    let agg = (orders, ticker, order_type, action) => orders.filter(order => 
                order.ticker == ticker && order.order_type == order_type && order.action == action)
    let reduce = (orders, filled) => orders.reduce((qty, order) => filled? order.qty_filled + qty: order.qty + qty, 0)

    let order_types = ['LMT', 'MKT']
    let actions = ['BUY', 'SELL']
    let filled = [false, true]
    // This looks way way way worse than it actually is 
    // Its actually really only o(N) where N is the variable number of openOrders 
    // all the others are small and fixed
    let aggregations = []
    for(let ticker of tickers) {
        for(let order_type of order_types) {
            for(let action of actions) {
                let filtered_orders = agg(ordersToAgg, ticker, order_type, action)
                if(filtered_orders.length == 0) continue;
                let qty = reduce(filtered_orders, false)
                let qty_filled = reduce(filtered_orders, true)
                aggregations.push({'ticker': ticker, 'order_type': order_type, 'action': action, 'qty': qty, 'qty_filled': qty_filled})
            }
        }
    }

    return aggregations
}

export default {
  name: 'OpenOrders',
  components: {
      BaseCard, CardTable
  },
  mixins: [HighlightTable],
  data: function() {
      return {
        contentHeaders: ['Ticker', 'Type', 'Action', 'Qty'],
        openOrderContentKeys: ['ticker','order_type','action','qty_filled_and_qty'],
        completedOrderContentKeys: ['ticker','order_type','action','qty'],
      }
  },
  computed: {
    ...mapGetters({
        tickers: 'backend/getTickers',
        displayLimitBook: 'backend/displayLimitBook',
        displayMarketBook: 'backend/displayMarketBook',
        orderKeys: 'frontend/getTraderOpenOrderKeys',
        completedOrders: 'frontend/getTraderCompletedOrders',
    }),
    orders: function() {
        return this.orderKeys.map((orderKey) => {
            let side = orderKey.action == 'BUY'? 'bid_book':'ask_book'
            let display_fn = orderKey.order_type == "LMT"? this.displayLimitBook: this.displayMarketBook
            
            let orders= display_fn(orderKey.ticker)[side]
            let position = orders.findIndex(order => order.order_id == orderKey.order_id)

            if (position == -1) {
                return undefined
            } else {
                let order = orders[position]
                order.queue_position = position
                return order
            }

            return undefined
        }).filter(order => order !== undefined)
    },
    // We will simply remove cancelled orders in vuex as they are not so useful
    openOrders: function() {
        return this.orders.filter(order => order.qty_filled !== order.qty)
    },
    openOrdersAggregated: function() {
        return aggregate_order_qtys(this.openOrders, this.tickers).map(order => {
            order['qty_filled_and_qty'] = `${order.qty_filled} / ${order.qty}`
            order['key'] = order.ticker + order.order_type  + order.action
            return order
        })
    },
    completedOrdersAggregated: function() {
        return aggregate_order_qtys(this.completedOrders, this.tickers).map(order => {
            order['key'] = order.ticker + order.order_type  + order.action
            return order
        })
    }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   

</style>
