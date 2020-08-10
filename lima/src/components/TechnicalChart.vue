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
                        :fill='colorOutline' 
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
                        :stroke='colorOutline' 
                        stroke-width='1'
                        opacity='0.2'
                     />
                </g>
                <!-- y-axis -->
                <g v-for="(tick, index) in yTicks" :key="'y-axis:' + tick">
                    <text 
                        :fill='colorOutline' 
                        :x='marginLeft / 4' 
                        :y='y(tick + 0.02)' 
                        opacity='0.6'
                    >{{tick}}</text>
                    <line v-if="index % 2 == 0"
                        x1='0'
                        :x2='x.range()[1]' 
                        :y1='y(tick)' 
                        :y2='y(tick) '
                        :stroke='colorOutline' 
                        stroke-width='1'
                        opacity='0.2'
                     />
                </g>
                <!-- candlesticks -->
                <g>
                    <g>
                        <!-- Real Body -->
                        <rect
                            v-for="body in realBodies"
                            :key="'body:' +body.xLabel"
                            :fill='body.fill'
                            :height='body.height'
                            :width='body.width'
                            :x='body.x'
                            :y='body.y'
                            :stroke='colorOutline' 
                            stroke-width='1'
                        ></rect>
                        <!-- Shadows -->
                        <line 
                            v-for="shadow in shadows"
                            :key="'shadow:' + shadow.xLabel"
                            :x1='shadow.x1'
                            :y1='shadow.y1'
                            :x2='shadow.x2'
                            :y2='shadow.y2'
                            :stroke='colorOutline' 
                            :stroke-dasharray='shadow.strokeDasharray'
                            stroke-width='2'
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
  name: 'TechnicalChart',
  props: {
      ticker: String, // security ticker to plot
      resolution: {default: 5, type: Number}, // Resolution of timestamps
      height: {default: 350, type: Number}, // Chart Size
      width: {default: 750, type: Number}, 
      marginLeft: {default: 48, type: Number}, // Chart margin for space for axis
      marginRight: {default: 8, type: Number},
      marginTop: {default: 16, type: Number},
      marginBottom: {default: 16, type: Number}, 
      candlestickPadding: {default: 0.3, type: Number}, // Gap between candles
      fillUptick: {default: 'white', type: String}, // Fill of candle on open > close
      fillDowntick: {default: '#19304F', type: String}, // Fill of candle on open < close
      colorOutline: {default: 'white', type: String}, // Color outline of candle
      showEveryKthPoint: {default: 10, type: Number}, // Shows every 10th Price Point
      maxPointsToShow: {default: 10, type: Number},
      showEveryKthTime: {default: 6, type: Number}, // Default 5s time interval -> show line every 30 seconds
      maxTimePeriodDisplay: {default: 120, type: Number} // Time in seconds
  },
  computed: {
    ...mapGetters({
        tickData: 'frontend/getTickData',
        securityParams: 'frontend/getSecurityParams',
        getTickerOHLC: 'frontend/getTickerOHLC'
    }),
    unfilteredOHLC: function() {
        return this.getTickerOHLC(this.ticker)
    },
    ohlc: function() {
        let lastTimestamp = Math.max(...this.unfilteredOHLC.map(candle => candle.timestamp))
        return this.unfilteredOHLC.filter(candle => candle.timestamp >= (lastTimestamp - this.maxTimePeriodDisplay))
    },
    securityResolution: function() {
        let params = this.securityParams(this.ticker)
        return params? params.resolution: 2
    },
    xTicks: function() {
        if(this.ohlc.length > 0) {
            let numXTicks = Math.floor(this.maxTimePeriodDisplay / this.resolution) + 1
            let xTickValues = [...Array(numXTicks).keys()].map(x => (this.ohlc[0].timestamp + (x * this.resolution)))
            
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
        let numXTicks = Math.floor(this.maxTimePeriodDisplay / this.resolution)
        let xTickValues = [...Array(numXTicks).keys()].map(x => (this.ohlc[0].timestamp + (x * this.resolution)))
        let x = d3.scaleBand()
            .domain(this.xTicks)
            .range([this.marginLeft, this.width - this.marginRight])
            .padding(this.candlestickPadding)
        
        return x
    },
    y: function() {
        let minLow = Math.min(...this.ohlc.map(tick => tick.l))
        let maxHigh = Math.max(...this.ohlc.map(tick => tick.h))

        // Y-axis is a continuous price scale
        let y = d3.scaleLinear()
            .domain([minLow-0.2, maxHigh+0.2])
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
    realBodies: function() {
        let bodies = this.ohlc.map(tick => {
            // (x,y) position of rect is top left corner
            let bodyHighestPoint = Math.max(...[tick.o, tick.c])
            
            return {
                xLabel: tick.timestamp,
                x: this.x(tick.timestamp),
                y: this.y(bodyHighestPoint),
                width: this.x.bandwidth(),
                height: Math.abs(this.y(tick.o) - this.y(tick.c)),
                fill: tick.c > tick.o? this.fillUptick: this.fillDowntick
            }
        })

        return bodies
    },  
    offset: function() {
        return this.x.bandwidth()/2
    },
    shadows: function() {
        let shadows = this.ohlc.map(tick => {
            let bodyHighestPoint = Math.max(...[tick.o, tick.c])
            let bodyLowestPoint = Math.min(...[tick.o, tick.c])
            
            let bodyHeight = Math.abs(this.y(tick.o) - this.y(tick.c))
            let lowerShadowHeight = Math.abs(this.y(bodyLowestPoint) - this.y(tick.l))
            let higherShadowHeight = Math.abs(this.y(tick.h) - this.y(bodyHighestPoint))

            return {
                xLabel: tick.timestamp,
                x1: this.x(tick.timestamp) + this.offset,
                y1: this.y(tick.l),
                x2: this.x(tick.timestamp) + this.offset,
                y2: this.y(tick.h),
                strokeDasharray: `${lowerShadowHeight} ${bodyHeight} ${higherShadowHeight}`
            }
        })

        return shadows
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
