<template>
    <BaseCard title='Time & Sales' :hasStats='false' :halfCard='false'>
        <template>
            <CardTable
            title='' 
            :tableHeaders="['Time', 'Ticker', 'Price', 'Type', 'Qty']"
            :itemKeys="['timestampRounded','ticker','price','action','qty']"
            :items='tapeReverse'
            :rowHighlight='highlightTraderTransactions'
            :cellHighlight='colorBuySell'
            >
            </CardTable>
        </template>
    </BaseCard>
</template>

<script>
import BaseCard from '../components/BaseCard.vue'
import CardTable from '../components/CardTable.vue'
import HighlightTable from '../mixins/HighlightTable'

import { mapGetters } from 'vuex'

export default {
  name: 'Tape',
  components: {
      BaseCard, CardTable
  },
  mixins: [HighlightTable],
  data: function() {
      return {
        boldStyle: {
            'font-weight': 'bold',
            'border-color': 'rgba(231, 193, 25, 0.945)',
            'font-style': 'italic'
        }
      } 
  },
  computed: {
    ...mapGetters({
        tape: 'frontend/displayTape',
        traderFills: 'frontend/getTraderFills'
    }),
    tapeReverse: function() {
      let sliceFrom = this.tape.length - Math.min(this.tape.length, 20)
      return this.tape.slice(sliceFrom).reverse()
    }
  }, 
  methods: {
    highlightTraderTransactions: function(transaction) {
        // Only one transaction is ever able to be processed at any given time
        let condition = this.traderFills.find(fill => fill.timestamp == transaction.timestamp) !== undefined

        return condition? this.boldStyle: {}
    }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   

</style>
