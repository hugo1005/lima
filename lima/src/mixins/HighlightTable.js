export default {
    data: function() {
        return {
            colorBuySell: function(key, transaction) {
                if(key == 'action') {
                    return transaction.action == 'BUY'? { color: '#46C38F' } : { color: '#EC7F6C' }
                }
                else return {}
            },
            canHighlightTransaction: function(transaction) {
                // Only one transaction is ever able to be processed at any given time
                return transaction.action == 'BUY'? {'border-color': '#46C38F'}: {'border-color': '#EC7F6C'}
            },
            highlightBidAsk(key, item) {
                if(key == 'best_bid' | key == 'best_ask') {
                    return { 'font-weight': 'bold', 'color': '#C9A647'} 
                }
                else return {}
            }
        }
    }
}