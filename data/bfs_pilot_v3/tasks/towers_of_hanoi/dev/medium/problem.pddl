


(define (problem hanoi-4)
(:domain hanoi)
(:objects peg2 peg1 peg3 d2 d1 d4 d3 )
(:init
(smaller peg2 d2)
(smaller peg2 d1)
(smaller peg2 d4)
(smaller peg2 d3)
(smaller peg1 d2)
(smaller peg1 d1)
(smaller peg1 d4)
(smaller peg1 d3)
(smaller peg3 d2)
(smaller peg3 d1)
(smaller peg3 d4)
(smaller peg3 d3)
(smaller d1 d2)
(smaller d4 d2)
(smaller d3 d2)
(smaller d4 d1)
(smaller d3 d1)
(smaller d3 d4)
(clear peg1)
(clear peg3)
(clear d2)
(on d3 peg2)
(on d4 d3)
(on d1 d4)
(on d2 d1)
)
(:goal
(and 
(on d3 peg3)
(on d4 d3)
(on d1 d4)
(on d2 d1)
)
)
)


