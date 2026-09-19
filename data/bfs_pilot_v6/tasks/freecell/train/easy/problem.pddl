(define (problem freecell-f1-c2-s1-i1-02
)(:domain freecell)
(:objects 
          C0 CA C2
 - card
          CELLN0 CELLN1 
 - cellnum
          COLN0 COLN1 COLN2 
 - colnum
          N0 N1 N2 
 - num
           C
 - suit
)
(:init
(VALUE C0 N0)
(VALUE CA N1)
(VALUE C2 N2)
(CELLSUCCESSOR CELLN1 CELLN0)
(COLSUCCESSOR COLN1 COLN0)
(COLSUCCESSOR COLN2 COLN1)
(SUCCESSOR N1 N0)
(SUCCESSOR N2 N1)
(HASSUIT C0 C)
(HASSUIT CA C)
(HASSUIT C2 C)
(HOME C0)
(CELLSPACE CELLN1)
(COLSPACE COLN1)

(BOTTOMCOL CA)
(ON C2 CA)
(CLEAR C2)
)
(:goal
(and
(HOME C2)
)
)
)
