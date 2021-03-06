(function ($) {
    $(document).ready(function () {
        var $nodeGraphs = $('.node-graphs');
        $nodeGraphs.datastream({
            'streamListUri': $nodeGraphs.data('source'),
            'streamListParams': {
                'tags__visualization__hidden__ne': true,
                'tags__node': $nodeGraphs.data('node'),
                // TODO: We currently support only line visualization type
                'tags__visualization__type': 'line',
                // More streams per page.
                'limit': 100
            }
        });
    });
})(jQuery);
