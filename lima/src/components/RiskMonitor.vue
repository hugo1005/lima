<template>
    <BaseCard title='Risk Monitor' :hasStats='true' :halfCard='false'>
        <template #stats>
            <CardTable
            title='Risk' 
            :tableHeaders="['Net Pos', 'Gross Pos','Unrealised','Realised', 'P&L']"
            :itemKeys="['net_position','gross_position','unrealised','realised','pnl']"
            :items='[risk]'
            ></CardTable>
        </template>
        <template>
            <CardTable
            title='Positions' 
            :tableHeaders="['Ticker', 'Net Pos', 'Unrealised', 'Realised', 'P&L']"
            :itemKeys="['ticker','net_position','unrealised','realised','total_pnl']"
            :items='pnl'
            itemUniqueIdentifer='ticker'
            ></CardTable>
        </template>
    </BaseCard>
</template>

<script>
import BaseCard from '../components/BaseCard.vue'
import CardTable from '../components/CardTable.vue'

import { mapGetters } from 'vuex'

export default {
  name: 'RiskMonitor',
  components: {
      BaseCard, CardTable
  },
  computed: {
    ...mapGetters({
        risk: 'frontend/getRisk',
        pnl: 'frontend/getPnL',
    }),
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   
    
</style>
