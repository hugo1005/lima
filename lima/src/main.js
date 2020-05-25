import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import { mapGetters } from 'vuex'

Vue.config.productionTip = false

const app = new Vue({
  router,
  store,
  computed: {
    ...mapGetters({
      getTID: 'frontend/getTID'
    }),
  },
  watch: {
    // Route to the trader view when a trader frontend is in operation
    getTID: function(newTID, oldTID) {
      console.log(newTID)

      if(newTID !== null) {
        console.log(`Tid: ${newTID}`)
        if(this.$router.currentRoute.path !== '/trader') this.$router.push('/trader')
      } else {
        this.$router.push('/observer')
      }
    }
  },
  render: h => h(App),
}).$mount('#app')
