


(define (problem gripper-2)
(:domain gripper-strips)
(:objects  rooma roomb left right ball2 ball1 )
(:init
(room rooma)
(room roomb)
(gripper left)
(gripper right)
(ball ball2)
(ball ball1)
(free left)
(free right)
(at ball2 rooma)
(at ball1 rooma)
(at-robby rooma)
)
(:goal
(and
(at ball2 roomb)
(at ball1 roomb)
)
)
)


