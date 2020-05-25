import Vue from 'vue'
import VueRouter from 'vue-router'
import Observer from '../views/Observer.vue'

Vue.use(VueRouter)

const routes = [
  {
    path: '/',
    alias: '/observer',
    name: 'Observer',
    component: Observer
  },
  {
    path: '/trader',
    name: 'Trader',
    // route level code-splitting
    // this generates a separate chunk (about.[hash].js) for this route
    // which is lazy-loaded when the route is visited.
    component: () => import(/* webpackChunkName: "about" */ '../views/Trader.vue')
  },
]

const router = new VueRouter({
  routes
})

export default router
