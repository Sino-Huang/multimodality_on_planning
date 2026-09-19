


(define (problem gripper-5)
(:domain gripper-strips)
(:objects  rooma roomb left right ball5 ball1 ball2 ball3 ball4 )
(:init
(room rooma)
(room roomb)
(gripper left)
(gripper right)
(ball ball5)
(ball ball1)
(ball ball2)
(ball ball3)
(ball ball4)
(free left)
(free right)
(at ball5 rooma)
(at ball1 rooma)
(at ball2 rooma)
(at ball3 rooma)
(at ball4 rooma)
(at-robby rooma)
)
(:goal
(and
(at ball5 roomb)
(at ball1 roomb)
(at ball2 roomb)
(at ball3 roomb)
(at ball4 roomb)
)
)
)


