<template>
    <div class='card'>
        <h3>{{title}}</h3>
        <div class='card-tables'>
            <!-- Full card -->
            <div v-if='!halfCard' class='fullcard-container'>
                <div v-if="hasStats" class='non-scrollable'>
                    <slot name="stats"></slot>
                </div>
                <div class="scrollable">
                    <slot></slot>
                </div>
            </div>
            <!-- Half card -->
            <div v-if='halfCard' class='halfcard-container'>
                <div v-if="hasStats" class='non-scrollable'>
                    <slot name="statsLeft"></slot>
                </div>
                <div class="scrollable">
                    <slot name="contentLeft"></slot>
                </div>
            </div>
            <div v-if='halfCard' class='halfcard-container'>
                <div v-if="hasStats" class='non-scrollable'>
                    <slot name="statsRight"></slot>
                </div>
                <div class="scrollable">
                    <slot name="contentRight"></slot>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
  name: 'BaseCard',
  props: {
    title: String,
    halfCard: {type: Boolean, default: true},
    hasStats: {type: Boolean, deafult: true},
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>   
    .card{
        /* Layout and background for entire component*/
        display:flex;
        flex-direction: column;
        align-items: flex-start;
        background-color:#00214D; 

        /* Limit the width but expand as much as possible */
        max-width: 500px;
        width: 100%;

        /* Some space styling */
        margin: 16px;
        border-radius: 8px;
        box-shadow: 6px 6px 16px rgba(0,0,0,0.16);
        padding-bottom: 16px;
    }
    
    .card-tables{
        /* Align the tables horizontally / side by side */
        display:flex;
        flex-direction: row;

        /* The captions of both tables will be the darkest part */
        background-color:#001634;
        border-radius: 8px;

        /* Ensure they make the most use of the allocated space*/
        width: 100%;
    }

    h3 {
        /* Make sure we have a white roboto font (same for table headers) */
        color: white;
        font-family: Roboto Slab;
        font-weight: normal;
        font-size: 20px;
        
        /* Indent by 16px same goes for the table headers */
        margin:0;
        margin-left: 16px;
    }

    /* Container for book and book stats */
    .fullcard-container {
        width: 100%;
    }

    .halfcard-container {
        width: 50%;
    }


    /* Scrolling Styles Only */
    .scrollable-parent {
        overflow: hidden;
        margin-right: 0;
    }

    .scrollable {
        width: 100%;
        max-height: 300px; 
        overflow-y: scroll;
        overflow-x: hidden;
    }

    .scrollable::-webkit-scrollbar {
        display: none;
    }

    /*  A trick for nice border lines :) */
    .non-scrollable {
        overflow-x: hidden
    }
</style>
