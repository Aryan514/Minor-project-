# report/word_finalize.ps1
# Opens the generated report in Microsoft Word (COM), formats the built-in TOC / Table of Figures styles
# (Times New Roman 12 pt, 1.5 lines), updates all fields (TOC, List of Figures, List of Tables, SEQ captions, PAGE),
# saves the .docx, exports the PDF and prints the page count and the page of every chapter heading.
param([string]$Docx = "$PSScriptRoot\Minor_Project_Report.docx")
$pdf = [System.IO.Path]::ChangeExtension($Docx, ".pdf")
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($Docx)
    foreach ($id in -20, -21, -22, -36) {          # wdStyleTOC1..3, wdStyleTableOfFigures
        $s = $doc.Styles.Item($id)
        $s.Font.Name = "Times New Roman"; $s.Font.Size = 12
        $s.ParagraphFormat.LineSpacingRule = 1        # wdLineSpace1pt5
        $s.ParagraphFormat.SpaceAfter = 0
    }
    for ($pass = 0; $pass -lt 2; $pass++) {
        $doc.Fields.Update() | Out-Null
        foreach ($t in $doc.TablesOfContents) { $t.Update() }
        foreach ($t in $doc.TablesOfFigures) { $t.Update() }
        $doc.Repaginate()
    }
    $doc.Save()
    $doc.ExportAsFixedFormat($pdf, 17)               # wdExportFormatPDF
    "pages: " + $doc.ComputeStatistics(2)
    "sections: " + $doc.Sections.Count
    foreach ($sec in $doc.Sections) {
        $ps = $sec.PageSetup
        "  section {0}: margins L{1:N2} T{2:N2} R{3:N2} B{4:N2} cm; numbering style {5}, restart {6}, start {7}" -f $sec.Index,
            ($ps.LeftMargin / 28.3465), ($ps.TopMargin / 28.3465), ($ps.RightMargin / 28.3465), ($ps.BottomMargin / 28.3465),
            $sec.Footers.Item(1).PageNumbers.NumberStyle, $sec.Footers.Item(1).PageNumbers.RestartNumberingAtSection,
            $sec.Footers.Item(1).PageNumbers.StartingNumber
    }
    foreach ($p in $doc.Paragraphs) {
        if ($p.OutlineLevel -eq 1 -or ($p.Range.Text -match '^TABLE OF CONTENTS')) {
            $r = $p.Range
            "  p.{0,-4} (abs {1,3})  {2}" -f $r.Information(1), $r.Information(3), $r.Text.Trim()
        }
    }
    "figures: " + ($doc.InlineShapes.Count) + "  tables: " + $doc.Tables.Count
    $doc.Close()
} finally {
    $word.Quit()
}
