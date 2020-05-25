<template>
    <div>
        {{ticker}}
    </div>
</template>

<script>
import { mapGetters } from 'vuex'

export default {
  name: 'TechnicalChart',
  props: {
      ticker: String,
  },
  computed: {
    //   ...mapGetters({
    //       ohlc: `backend/getTickData${this.ticker}`,
    //   })
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   

</style>
