(defun c:SLD2SAP ( / ss fname file ent i elst enttype coords minPt maxPt bl br tr tl texts textObj textPt textContent resultText allTexts cirCenter cirRadius cirText cirResultText )

  ;; Ask user to select objects
  (prompt "\nSelect objects (rectangles, circles, and texts in TAGGED_LOADS layer): ")
  (setq ss (ssget '((8 . "TAGGED_LOADS") (0 . "LWPOLYLINE,CIRCLE,TEXT,MTEXT"))))

  (if (not ss)
    (progn (prompt "\nNothing selected.") (princ))
  )

  ;; Ask user for output file path
  (setq fname (getfiled "Save CSV File" "Loads_Export.csv" "csv" 1))

  (if fname
    (progn
      ;; Open file for writing
      (setq file (open fname "w"))
      (write-line "Index,X1,Y1,X2,Y2,X3,Y3,X4,Y4,Text1,Text2,Text3,Text4,Text5" file)
      (setq i 0)

      ;; Extract all texts from selection (to filter faster)
      (setq allTexts '())
      (while (< i (sslength ss))
        (setq ent (ssname ss i))
        (setq elst (entget ent))
        (setq enttype (cdr (assoc 0 elst)))
        (if (or (equal enttype "TEXT") (equal enttype "MTEXT"))
          (setq allTexts (cons elst allTexts))
        )
        (setq i (1+ i))
      )
      
      (setq i 0)
      (setq index 1)

      ;; Loop through all selected objects again
      (while (< i (sslength ss))
        (setq ent (ssname ss i))
        (setq elst (entget ent))
        (setq enttype (cdr (assoc 0 elst)))

        (cond
          ;; --- RECTANGLES ---
          ((equal enttype "LWPOLYLINE")
            (setq coords '())
            (foreach pair elst
              (if (eq (car pair) 10)
                (setq coords (cons (cdr pair) coords))
              )
            )
            (setq coords (reverse coords))

            (if (= (length coords) 4)
              (progn
                ;; Min/max corners
                (setq minPt (car coords))
                (setq maxPt minPt)
                (foreach pt coords
                  (setq minPt (list (min (car pt) (car minPt)) (min (cadr pt) (cadr minPt))))
                  (setq maxPt (list (max (car pt) (car maxPt)) (max (cadr pt) (cadr maxPt))))
                )
                (setq bl (list (car minPt) (cadr minPt))) ; Down Left ??
                (setq br (list (car maxPt) (cadr minPt))) ; Down Right
                (setq tr (list (car maxPt) (cadr maxPt))) ; Top Right
                (setq tl (list (car minPt) (cadr maxPt))) ; Top Left
                ;; Find texts inside rectangle
                (setq texts '())
                (foreach textObj allTexts
                  (setq textPt (cdr (assoc 10 textObj)))
                  (if (and (>= (car textPt) (car minPt)) (<= (car textPt) (car maxPt))
                           (>= (cadr textPt) (cadr minPt)) (<= (cadr textPt) (cadr maxPt)))
                    (progn
                      (setq textContent
                        (cond
                          ((assoc 1 textObj) (cdr (assoc 1 textObj)))  ; TEXT
                          ((assoc 3 textObj) (cdr (assoc 3 textObj)))  ; MTEXT
                          (T "")
                        )
                      )
                      (setq texts (append texts (list textContent)))
                    )
                  )
                )
                ;; Ensure 5 text fields
                (while (< (length texts) 5)
                  (setq texts (append texts (list "")))
                )
                (setq resultText (list (nth 0 texts) (nth 1 texts) (nth 2 texts) (nth 3 texts) (nth 4 texts)))

                ;; Write to file
                (write-line
                  (strcat
                    (itoa index) ","
                    (rtos (car bl) 2 3) "," (rtos (cadr bl) 2 3) ","
                    (rtos (car br) 2 3) "," (rtos (cadr br) 2 3) ","
                    (rtos (car tr) 2 3) "," (rtos (cadr tr) 2 3) ","
                    (rtos (car tl) 2 3) "," (rtos (cadr tl) 2 3) ","
                    "\"" (car resultText) "\","
                    "\"" (cadr resultText) "\","
                    "\"" (caddr resultText) "\","
                    "\"" (nth 3 resultText) "\","
                    "\"" (nth 4 resultText) "\""
                  )
                  file
                )
                (setq index (1+ index))
              )
            )
          )

          ;; --- CIRCLES ---
          ((equal enttype "CIRCLE")
            (setq cirCenter (cdr (assoc 10 elst)))
            (setq cirRadius (cdr (assoc 40 elst)))

            ;; Find 2 texts inside circle
            (setq cirText '())
            (foreach textObj allTexts
              (setq textPt (cdr (assoc 10 textObj)))
              (if (<= (distance textPt cirCenter) cirRadius)
                (progn
                  (setq textContent
                    (cond
                      ((assoc 1 textObj) (cdr (assoc 1 textObj)))  ; TEXT
                      ((assoc 3 textObj) (cdr (assoc 3 textObj)))  ; MTEXT
                      (T "")
                    )
                  )
                  (setq cirText (append cirText (list textContent)))
                )
              )
            )
            (while (< (length cirText) 2)
              (setq cirText (append cirText (list "")))
            )
            (setq cirResultText (list (nth 0 cirText) (nth 1 cirText)))

            ;; Write to file: set X2,Y2,X3,Y3,X4,Y4 empty
            (write-line
              (strcat
                (itoa index) ","
                (rtos (car cirCenter) 2 3) "," (rtos (cadr cirCenter) 2 3) ","
                ",,,,,," 
                "\"" (car cirResultText) "\","
                "\"" (cadr cirResultText) "\","
                "\"\","
                "\"\","
                "\"\""
              )
              file
            )
            (setq index (1+ index))
          )
        )
        (setq i (1+ i))
      )
      (close file)
      (prompt (strcat "\nData exported to: " fname))
    )
    (prompt "\nCanceled.")
  )

  (princ)
)