function buildTraceChart(traces) {

    let urls = traces.map(trace => trace.url)

    urls = urls.filter(
        (item, index) => urls.indexOf(item) === index
    )

    let datasets = urls.map((url) => {
        return {
            label: url,
            data: traces.map(trace => {
                if (trace.url == url) {
                    return {
                        x: new Date(trace.time).getTime(),
                        y: trace.duration,
                        id: trace.id
                    }
                }
            }),
            pointRadius: 5,
            backgroundColor: 'rgb(255, 99, 132)'
        }
    })

    const data = {
        datasets: datasets,
    };

    const config = {
        type: 'scatter',
        data: data,
        options: {
            onClick: (p, e) => {
                if (e[0]) {
                    location.href = '/trace/' + e[0].element.$context.raw.id
                }
            },
            plugins: {
                colors: {
                    enabled: false
                }
            },
            scales: {
                x: {
                    type: 'time',



                    ticks: {
                        autoSkip: true,
                        maxTicksLimit: 10
                    }
                }
            }
        }
    };
    const myChart = new Chart(document.getElementById('tracing'), config);
}
