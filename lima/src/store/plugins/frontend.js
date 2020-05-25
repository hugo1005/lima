const client = new WebSocket(process.env.VUE_APP_FRONTEND_WEBSOCKET_URL)

export default function createWebSocketPlugin() {
    return store => {
        client.onopen = function() {
            store.dispatch('frontend/connectionOpened')
        }

        client.onerror = function(event) {
            store.dispatch('frontend/connectionError', event)
        }
        
        client.onmessage = function(event) {
            let msg = JSON.parse(event.data)

            // Note these actions are for display purposes only
            // They do not change backend / frontend state
            if(msg.type == 'config') {
                store.dispatch('frontend/updateTID', msg.data.tid)
            } else if(msg.type == 'order_opened') {
                store.dispatch('frontend/registerOrder', msg.data)
            } else if(msg.type == 'order_fill') {
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
        }

        // An example for communicating back:
        // Link: http://iamnotmyself.com/2020/02/14/implementing-websocket-plugins-for-vuex/
        // Link: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_client_applications
        // store.subscribe((mutation, state) => {
        //     if (state.chat.connected && mutation.type === 'chat/SEND_MESSAGE')
        //       client.invoke('SendMessage', null, message);
        //   });
    }
}