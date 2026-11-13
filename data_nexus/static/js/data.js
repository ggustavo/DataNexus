const debug = false;

const URL = (typeof window !== 'undefined' && window.location && window.location.protocol.startsWith('http'))
    ? window.location.origin
    : 'http://localhost:5000';

let headers = new Headers();
headers.append("Content-Type", "application/json");

function requestOptions(){ 
    return {
        method: 'POST',
        headers: headers,
        redirect: 'follow',
    };
}

function request_connection(connection, call) {
    if (debug) return debug_request_connection(connection, call);

    let ro = requestOptions();
    ro.body = JSON.stringify(connection);

    fetch(URL + "/validate_connection", ro)
    .then(response => {
        //console.log('Response status:', response.status);
        return response.text();
    })
    .then(result => {
        // console.log('Result:', result);
        if (result != null) {
            result = JSON.parse(result);
            
            if (result.error) {
                showErrorModal(result.error);
            } else {
                connection.id = result.id;
                call(connection);
            }
        }
    }) 
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });
}


function request_connections(call) {
    if (debug) return debug_request_connections(call);
    let ro = requestOptions();
    ro.method = 'POST';

    fetch(URL + "/connections", ro)
    .then(response => {
        //console.log('Response status:', response.status);
        return response.text();
    })
    .then(result => {
        //console.log('Result:', result);
        if (result != null) {
            result = JSON.parse(result);
            
            if (result.error) {
                showErrorModal(result.error);
            } else {
                call(result);
            }
        }
    }) 
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });

}

function request_graph_data(connection, type, centrality_type, call) {
    if (debug) return debug_request_graph_data(connection, type, call);

    let ro = requestOptions();
    ro.body = JSON.stringify({
        "id":connection.id,
        "type":type,
        "centrality_type": centrality_type
    });

    fetch(URL + "/graph", ro)
    .then(response => {
        //console.log('Response status:', response.status);
        return response.text();
    })
    .then(result => {
        // console.log('Result:', result);
        if (result != null) {
            result = JSON.parse(result);
            
            if (result.error) {
                showErrorModal(result.error);
            } else {
                //console.log(result);
                call(result);
            }
        }
    }) 
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });
    
}



function request_table_metadata(connection, name, call) {
    

    let ro = requestOptions();
    ro.body = JSON.stringify({
        "id":connection.id,
        "name":name
    });

    fetch(URL + "/metadadata", ro)
    .then(response => {
        //console.log('Response status:', response.status);
        return response.text();
    })
    .then(result => {
        // console.log('Result:', result);
        if (result != null) {
            result = JSON.parse(result);
            
            if (result.error) {
                showErrorModal(result.error);
            } else {
                //console.log(result);
                call(result);
            }
        }
    }) 
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });
    
}


function request_relationship_config(connection_id, call) {
    let ro = requestOptions();
    ro.body = JSON.stringify({
        "id": connection_id
    });

    fetch(URL + "/relationship_config", ro)
    .then(response => response.text())
    .then(result => {
        if (result != null) {
            result = JSON.parse(result);
            if (result.error && !result.has_cache) {
                showErrorModal(result.error);
            } else if (result.error) {
                showErrorModal(result.error);
            } else {
                call(result);
            }
        }
    })
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });
}


function request_save_relationship_config(connection_id, enabled, column_settings, call) {
    let ro = requestOptions();
    ro.body = JSON.stringify({
        "id": connection_id,
        "enabled": enabled,
        "column_settings": column_settings
    });

    fetch(URL + "/save_relationship_config", ro)
    .then(response => response.text())
    .then(result => {
        if (result != null) {
            result = JSON.parse(result);
            if (result.error) {
                showErrorModal(result.error);
            } else {
                call(result);
            }
        }
    })
    .catch(error => {
        console.log('Error:', error);
        showErrorModal(error);
    });
}
