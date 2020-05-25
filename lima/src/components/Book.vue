<template>
    <BaseCard :title="ticker + ` [${orderType}]`" v-if="book !== undefined" :hasStats='isLimitBook'>
        
        <template v-if="isLimitBook" #statsLeft>
            <CardTable
            title='Bids' 
            :tableHeaders="['Vol', 'Depth', 'Best Bid']"
            :itemKeys="['bid_volume','bid_depth','best_bid']"
            :items='[book]'
            :cellHighlight='highlightBidAsk'
            ></CardTable>
        </template>
        
        <template #contentLeft>
            <CardTable 
            :title="isLimitBook? 'Book': 'Bids'"
            :tableHeaders="contentHeaders"
            :itemKeys="contentKeys"
            :items='bidBook'
            itemUniqueIdentifer='order_id'
            ></CardTable>
        </template>

        <template v-if="isLimitBook" #statsRight>
            <CardTable
            title='Asks' 
            :tableHeaders="['Best Ask', 'Depth', 'Vol']"
            :itemKeys="['best_ask','ask_depth','ask_volume']"
            :items='[book]'
            accentColor = '#EC7F6C'
            accentBg = 'rgba(236, 127, 108, 0.3)'
            :cellHighlight='highlightBidAsk' 
            ></CardTable>
         </template>

        <template #contentRight>
            <CardTable
            :title="isLimitBook? 'Book': 'Asks'"
            :tableHeaders="contentHeaders"
            :itemKeys="contentKeys"
            :items='askBook'
            itemUniqueIdentifer='order_id'
            accentColor = '#EC7F6C'
            accentBg = 'rgba(236, 127, 108, 0.3)'
            ></CardTable>
        </template>

    </BaseCard>
</template>

<script>
import BaseCard from '../components/BaseCard.vue'
import CardTable from '../components/CardTable.vue'
import HighlightTable from '../mixins/HighlightTable'

export default {
  name: 'Book',
  components: {
      BaseCard, CardTable
  },
  mixins: [HighlightTable],
  props: {
    ticker: String,
    asLadder: {type: Boolean, default: false},
    orderType: {
        type: String,
        default: 'LMT',
        validator: function (value) {
            // The value must match one of these strings
            return ['LMT', 'MKT'].indexOf(value) !== -1
        } 
    }
  },
  computed: {
    bookType: function() {
        return this.orderType == 'LMT' ? 'LimitBook' : 'MarketBook'
    },
    book: function() {
        return this.$store.getters[`backend/display${this.bookType}`](this.ticker)
    },
    bidBook: function() {
        return this.book.bid_book.map(order => {
            order['qty_filled_and_qty'] = `${order.qty_filled} / ${order.qty}`
            return order
        })
    },
    askBook: function() {
        return this.book.ask_book.map(order => {
            order['qty_filled_and_qty'] = `${order.qty_filled} / ${order.qty}`
            return order
        })
    },
    isLimitBook: function() {
        return this.orderType == 'LMT'
    },
    contentHeaders: function() {
        return this.isLimitBook ? ['Order ID', 'Price', 'Qty']: ['Order ID', 'Qty']
    },
    contentKeys: function() {
        return this.isLimitBook ? ['order_id','price','qty_filled_and_qty']: ['order_id','qty_filled_and_qty']
    }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   
    
</style>
