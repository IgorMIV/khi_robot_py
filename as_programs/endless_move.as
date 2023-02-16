.PROGRAM endless_move()
  ; *******************************************************************
  ;
  ; Program:      endless
  ; Comment:
  ; Author:       User
  ;
  ; Date:         2/3/2023
  ;
  ; *******************************************************************
  ;
  POINT mv1 = HERE
  SPEED 1 mm/s ALWAYS
  WHILE TRUE DO
    JMOVE mv1
  END
.END

