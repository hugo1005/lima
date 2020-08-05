def improve_on_best_quote(edge):
    """
    Generates a limit price that slightly improves on the best quoted price from the exchange
    :param edge: How much to improve on the best price by
    :return compute_price: A function that dynamically computes the limit price as function of (direction ~ {-1,0,1}, evaluate ~ Security.evaluate)
    """
    def compute_price(direction, evaluate):
        # If direction = 1 => subtract edge from best bid
        return round(evaluate(direction) - direction * edge,2)

    return compute_price