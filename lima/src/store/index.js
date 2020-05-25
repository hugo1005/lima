import Vue from 'vue'
import Vuex from 'vuex'

import backend from './modules/backend'
import frontend from './modules/frontend'
import backendSocket from './plugins/backend'
import frontendSocket from './plugins/frontend'

Vue.use(Vuex)

export default new Vuex.Store({
    modules: {
      backend,
      frontend
    },
    plugins: [backendSocket(), frontendSocket()]
})
