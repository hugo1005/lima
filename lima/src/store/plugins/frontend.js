export default function createWebSocketPlugin() {
    return store => {
        function connect() {
            let client = new WebSocket(process.env.VUE_APP_FRONTEND_WEBSOCKET_URL);
            
            client.onopen = function() {
                store.dispatch('frontend/connectionOpened')
            }
    
            client.onerror = function(event) {
                store.dispatch('frontend/connectionError', event)
            }

            client.onclose = function() {
                console.log("Connection with frontend closed...")
                store.dispatch('frontend/connectionClosed')
    
                setTimeout(function() {
                    connect();
                }, 500);
            };
            
            client.onmessage = function(event) {
                let msg = JSON.parse(event.data)
    
                // Note these actions are for display purposes only
                // They do not change backend / frontend state
                if(msg.type == 'config') {
                    store.dispatch('frontend/updateTID', msg.data.tid)
                } 
                else if(msg.type == 'order_opened') {
                    store.dispatch('frontend/registerOrder', msg.data)
                } 
                else if(msg.type == 'order_fill') {
                    store.dispatch('frontend/fillOrder', msg.data)
                }
                else if(msg.type == 'order_completed') {
                    store.dispatch('frontend/completeOrder', msg.data)
                }
                else if(msg.type == 'risk') {
                    store.dispatch('frontend/updateRisk', msg.data)
                }
                else if(msg.type == 'pnl') {
                    store.dispatch('frontend/updatePnL', msg.data)
                }
                else if(msg.type == 'product_update') {
                    store.dispatch('frontend/updateProduct', msg.data)
                }
                else if(msg.type == 'config') {
                    store.dispatch('frontend/configBackend', msg.data)
                }
                else if(msg.type == 'LOBS') {
                    store.dispatch('frontend/updateLimitBook', msg.data)
                }
                else if(msg.type == 'tape') {
                    store.dispatch('frontend/updateTape', msg.data)
                }
                else if(msg.type == 'traders') {
                    store.dispatch('frontend/updateTraders', msg.data)
                }
                else if(msg.type == 'current_time') {
                    store.dispatch('frontend/updateTime', msg.data)
                } 
            }
        }
        
        // Actually open the new socket!
        connect()
    }
}