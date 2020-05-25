<template> 
        <table>
            <tr v-if='title'>
                <th colspan="3" class="caption" :style="{color: accentColor}">{{title}}</th>
            </tr>
            <tr>
                <th v-for="header in tableHeaders" :key="header" :style='stickyHeaderStyle'>{{header}}</th>
            </tr>
            <tr v-for="(item, jdx) in items" :key="jdx" :style="styleRow(item)" :class='rowClassStyle'>
                <td 
                v-for="(itemKey, idx) in itemKeys" 
                :key="itemUniqueIdentifer?itemKey[itemUniqueIdentifer]:idx" :style="cellHighlightStyle(itemKey, item)">
                {{item[itemKey]}}
                </td>
            </tr>
        </table>
</template>

<script>
export default {
  name: 'CardTable',
  props: {
      title: String,
      accentColor: {default: '#46C38F', type: String}, // Alt: #EC7F6C (Red)
      accentBg: {default: 'rgba(70, 195, 143, 0.3)', type: String}, // Alt: rgba(236, 127, 108, 0.3) (Red)
      leftBorder: {default: true, type: Boolean},
      rightBorder: {default: false, type: Boolean},
      items: Array, // Must be an array of dicts
      itemKeys: Array,
      rowHighlight: {default: (item)=>{return {}}, type: Function},
      cellHighlight: {default: (itemKey, item)=>{return {}}, type: Function},
      tableHeaders: Array, // Array of strings
      itemUniqueIdentifer: {default:'', type:String}, // The :key field on the loop
      maxScrollItemsDisplay: {default: 10, type: Number},
      scrollKeyField: String
  },
  computed: {
      cssVars: function() {
          return {'--accent-bg': this.accentBg, '--accent-color': this.accentColor}
      },
      stickyHeaderStyle: function() {
          return {
                'color':'white',
                'position': 'sticky',
                'z-index': 2,
                'top': this.title? '32px': '0px'
            }
      },
      rowClassStyle: function() {
          return {
              highlight: true,
              accentBorderLeft: this.leftBorder,
              accentBorderRight: this.rightBorder,
          }
      }
  },
  methods: {
      rowHighlightStyle: function(item) {
          return this.rowHighlight(item)
      },
      cellHighlightStyle: function(itemKey, item) {
          return this.cellHighlight(itemKey, item)
      },
      styleRow: function(item) {
          return {...this.cssVars, ...this.rowHighlightStyle(item)}
      }
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   
    table {
        color: white;

        /* Make sure the borders vanish */
        border-collapse: collapse;

        /* There are two tables so each should allocate as much space as possible */
        width: 100%;
    }

    /* Container for book and book stats */
    /* Keep the headers visible */

    .caption{
        position: sticky;
        z-index: 2;
        top: 0px;
    }

    .stat-headers th{
        color:white;
        position: sticky;
        z-index: 2;
        top: 32px;
    }

    /* Table Stripes */
    table tr {
        height: 32px;
        /* A slightly more grey color for table entries */
        color: #D3D3D3;
    }

    table tr:nth-child(odd) {background-color: #002252; }
    table tr:nth-child(even) {background-color: #192F4E;}

    table th{
        background-color: #001B41;
        color: white;
    }
    
    table .caption {
        font-family: Roboto Slab;
        font-size: 20px;
        font-weight: normal;
        padding-left: 16px;
        text-align: left;
        background-color: #001634;
    }

    .accentBorderLeft {
        border-left: 4px solid var(--accent-color);
    }

    .accentBorderLeft:hover {
        border-left-width: 8px;
    }

    .accentBorderRight {
        border-right: 4px solid var(--accent-color);
    }

    .accentBorderRight:hover {
        border-right-width: 8px;
    }


    .highlight:hover {
        background-color:var(--accent-bg);
    }
</style>
