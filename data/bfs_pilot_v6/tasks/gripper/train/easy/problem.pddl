


(define (problem gripper-2)
(:domain gripper-strips)
(:objects  roomb rooma right left ball1 ball2 )
(:init
(room roomb)
(room rooma)
(gripper right)
(gripper left)
(ball ball1)
(ball ball2)
(free right)
(free left)
(at ball1 roomb)
(at ball2 roomb)
(at-robby roomb)
)
(:goal
(and
(at ball1 rooma)
(at ball2 rooma)
)
)
)


