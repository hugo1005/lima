<template>
    <div id='chart'>
        <h3 class='caption'>
            {{ticker}}
        </h3>
        <div id='chart-container'>
            <svg :height='height' :width='width'>
                <!-- x-axis -->
                <!-- Naming of keys avoids key clashes across the several v-for loops -->
                <g v-for="(timestamp, index) in xTicks" :key="'x-axis:' + timestamp">
                    <text 
                        v-if="index % 2 == 0"
                        fill='white' 
                        :x='x(timestamp) + offset' 
                        :y='height - (marginBottom / 2) ' 
                        opacity='0.6'
                        text-anchor='middle'
                    >{{timestamp}}</text>
                    <line
                        :x1='x(timestamp) + offset'
                        :x2='x(timestamp) + offset' 
                        :y1='0' 
                        :y2='height'
                        stroke='white' 
                        stroke-width='1'
                        opacity='0.2'
                     />
                </g>
                <!-- y-axis -->
                <g v-for="(tick, index) in yTicks" :key="'y-axis:' + tick">
                    <text 
                        fill='white' 
                        :x='marginLeft / 4' 
                        :y='y(tick + 0.02)' 
                        opacity='0.6'
                    >{{tick}}</text>
                    <line v-if="index % 2 == 0"
                        x1='0'
                        :x2='x.range()[1]' 
                        :y1='y(tick)' 
                        :y2='y(tick) '
                        stroke='white'  
                        stroke-width='1'
                        opacity='0.2'
                     />
                </g>
                <!-- Product time series data -->
                <g>
                    <g>
                        <path
                            :d = 'bidLine'
                            :stroke='colorBidLine'  
                            stroke-width='2'
                            fill="none"
                        />
                        <path
                            :d = 'askLine'
                            :stroke='colorAskLine'  
                            stroke-width='2'
                            fill="none"
                        />
                    </g>
                </g>
            </svg>
        </div>
    </div>
</template>

<script>
import { mapGetters } from 'vuex'
import { round } from 'mathjs'
import * as d3 from 'd3'

export default {
  name: 'ProductChart',
  props: {
      ticker: String, // security ticker to plot
      resolution: {default: 1, type: Number}, // Resolution of timestamps
      height: {default: 350, type: Number}, // Chart Size
      width: {default: 750, type: Number}, 
      marginLeft: {default: 48, type: Number}, // Chart margin for space for axis
      marginRight: {default: 8, type: Number},
      marginTop: {default: 16, type: Number},
      marginBottom: {default: 16, type: Number}, 
      colorBidLine: {default: '#46C38F', type: String}, // Color outline of candle
      colorAskLine: {default: '#EC7F6C', type: String}, // Color outline of candle
      showEveryKthPoint: {default: 10, type: Number}, // Shows every 10th Price Point
      maxPointsToShow: {default: 10, type: Number},
      showEveryKthTime: {default: 10, type: Number}, // Default 5s time interval -> show line every 30 seconds
      maxTimePeriodDisplay: {default: 30, type: Number} // Time in seconds
  },
  computed: {
    ...mapGetters({
        getProduct: 'frontend/getProduct'
    }),
    unfilteredProductBidAsk: function() {
        console.log("Getting product info!")
        return this.getProduct(this.ticker)
    },
    productBidAsk: function() {
        let lastTimestamp = Math.max(...this.unfilteredProductBidAsk.map(tick => tick.timestamp))
        return this.unfilteredProductBidAsk.filter(tick => tick.timestamp >= (lastTimestamp - this.maxTimePeriodDisplay))
    },
    securityResolution: function() {
        // Not going to be too important this should be good enough for most custom products...
        return 2
    },
    xTicks: function() {
        if(this.productBidAsk.length > 0) {
            
            let numXTicks = Math.floor(this.maxTimePeriodDisplay / this.resolution) + 1
            let xTickValues = [...Array(numXTicks).keys()].map(x => (this.productBidAsk[0].timestamp + (x * this.resolution)))
            return xTickValues
        } else {
            return []
        }
    },
    x: function() {
        // Very helpful tutorial for vuejs + d3
        // https://websiddu.com/blog/how-to-make-a-bar-chart-using-vue-js.html
        // Candlestick timestamps are discrete buckets so we us scaleBand
        // Padding sepearates the candles slighlty
        let x = d3.scaleBand()
            .domain(this.xTicks)
            .range([this.marginLeft, this.width - this.marginRight])
        
        return x
    },
    offset: function() {
        return 0
        // return this.x.bandwidth()/2
    },
    y: function() {
        let minLow = Math.min(...this.productBidAsk.map(tick => tick.best_bid))
        let maxHigh = Math.max(...this.productBidAsk.map(tick => tick.best_ask))
        console.log(minLow, maxHigh)

        let min =  Math.min(minLow, maxHigh)
        let max =  Math.max(minLow, maxHigh)
        
        // Y-axis is a continuous price scale
        let y = d3.scaleLinear()
            .domain([min-2, max+2])
            .range([this.height - this.marginBottom, this.marginTop]) // Make sure axis goes increasing from bottom to top of screen!
        
        return y
    },
    yTicks: function() {
        let domain = this.y.domain()
        let lower = domain[0]
        let upper = domain[1]
        
        // Displays a kth point where k = this.pointsVisible
        let pointsRange = (upper - lower) / Math.pow(10,-1*this.securityResolution)
        let numYTicks = Math.floor(pointsRange / this.showEveryKthPoint)
        return this.y.ticks(Math.min(numYTicks,this.maxPointsToShow))
    },
    bidLine: function() {
        return d3.line().x(tick => this.x(tick.timestamp)).y(tick => this.y(tick.best_bid))(this.productBidAsk)
    },
    askLine: function() {
        return d3.line().x(tick => this.x(tick.timestamp)).y(tick => this.y(tick.best_ask))(this.productBidAsk)
    }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   
    .caption {
        font-family: Roboto;
        font-size: 20px;
        font-weight: bold;
        padding-left: 16px;
        text-align: left;
        margin: 4px;
    }

    #chart {
        max-width: 750px;
        width: 100%;
        height: 100%;
        margin: 16px;
       
        background-color: #35537C;
        border-radius: 8px;
        box-shadow: 6px 6px 16px rgba(0,0,0,0.16);
    }

    #chart-container {
        background-color: #19304F;
    }
</style>
