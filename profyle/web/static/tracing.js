function buildTraceChart(traces) {

    let names = traces.map(trace => trace.name)

    names = names.filter(
        (item, index) => names.indexOf(item) === index
    )

    let datasets = names.map((name) => {
        return {
            label: name,
            data: traces.map(trace => {
                if (trace.name == name) {
                    return {
                        x: new Date(trace.time).getTime(),
                        y: trace.duration,
                        id: trace.id,
                        label: trace.label
                    }
                }
                return {}
            }),
            pointRadius: 5
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
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            let name = context.dataset.label;
                            let label = context.raw.label
                            return `${label} ${name} ${context.formattedValue}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    ticks: {
                        maxTicksLimit: 10
                    },
                    min: moment().subtract(1, 'week').format('YYYY-MM-DD kk:mm:ss'),
                    time: {
                        unit: 'day'
                    }
                }
            }
        }
    };
    const myChart = new Chart(document.getElementById('tracing'), config);
    const lastMinute = document.getElementById('last_minute')
    const lastHour = document.getElementById('last_hour')
    const lastDay = document.getElementById('last_day')
    const lastWeek = document.getElementById('last_week')
    const lastMonth = document.getElementById('last_month')

    lastMinute.addEventListener('click', () => {
        myChart.options.scales.x.min = moment().subtract(1, 'minute').format('YYYY-MM-DD kk:mm:ss')
        myChart.options.scales.x.time.unit = 'second'
        myChart.update()
    })

    lastHour.addEventListener('click', () => {
        myChart.options.scales.x.min = moment().subtract(1, 'hour').format('YYYY-MM-DD kk:mm:ss')
        myChart.options.scales.x.time.unit = 'second'
        myChart.update()

    })

    lastDay.addEventListener('click', () => {
        myChart.options.scales.x.min = moment().subtract(1, 'day').format('YYYY-MM-DD kk:mm:ss')
        myChart.options.scales.x.time.unit = 'minute'
        myChart.update()

    })

    lastWeek.addEventListener('click', () => {
        myChart.options.scales.x.min = moment().subtract(1, 'week').format('YYYY-MM-DD kk:mm:ss')
        myChart.options.scales.x.time.unit = 'day'
        myChart.update()

    })

    lastMonth.addEventListener('click', () => {
        myChart.options.scales.x.min = moment().subtract(1, 'month').format('YYYY-MM-DD kk:mm:ss')
        myChart.options.scales.x.time.unit = 'day'
        myChart.update()

    })
}
