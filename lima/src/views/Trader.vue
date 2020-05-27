<template>
  <div class="home">
    <!-- <h1>Traders</h1> -->
    <p>Trader View {{getTID}}</p>

    <!-- <h1>Books</h1> -->
    <div id='book-pair' style='max-height: 500px;'>
      <Book :ticker="ticker" orderType="LMT" v-for="ticker in tickers" v-bind:key="ticker"></Book>
    </div>
    <div id='book-pair'>
      <TechnicalChart :ticker="ticker" v-for="ticker in tickers" v-bind:key="ticker" :resolution='5'></TechnicalChart> 
    </div>
    <div id='book-pair' style='max-height: 450px;'>
      <Tape></Tape>
      <OpenOrders></OpenOrders>
      <RiskMonitor></RiskMonitor>
    </div>
    <div id='book-pair' style='max-height: 450px;'>
      <Book :ticker="ticker" orderType="MKT" v-for="ticker in tickers" v-bind:key="ticker"></Book>
    </div>
      
    
    
    <!-- <img alt="Vue logo" src="../assets/logo.png"> -->
    <!-- <HelloWorld msg="Welcome to Your Vue.js App"/> -->
  </div>
</template>

<script>
// @ is an alias to /src
import Book from '../components/Book.vue'
import Tape from '../components/Tape.vue'
import OpenOrders from '../components/OpenOrders.vue'
import RiskMonitor from '../components/RiskMonitor.vue'
import TechnicalChart from '../components/TechnicalChart.vue'
import { mapGetters } from 'vuex'

export default {
  name: 'Trader',
  components: {
    Book, Tape, OpenOrders, RiskMonitor, TechnicalChart
  },
  computed: {
    ...mapGetters({
      tickers: 'backend/getTickers',
      traders: 'backend/getTraders',
      tape: 'backend/displayTape',
      displayLimitBook: 'backend/displayLimitBook',
      displayMarketBook: 'backend/displayMarketBook',
      getTID: 'frontend/getTID'
    })

  }
}
</script>

<style scoped>
  #book-pair {
    display:flex;
    flex-direction: row;
    width: 100%;
  }

  #book-pair Book {
    display:flex;
    flex-direction: row;
    width: 50%;
  }
</style>