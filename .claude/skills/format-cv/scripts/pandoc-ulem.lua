-- Filtre Pandoc : rend le souligné et le barré avec le paquet ulem au lieu de soul,
-- qui plante sur les mises en forme imbriquées (ex. texte barré ET souligné).
-- Le barré est conservé : dans les ressources il signifie souvent « écarté ».
-- Usage : pandoc in.docx -o out.pdf --lua-filter=scripts/pandoc-ulem.lua -V header-includes='\usepackage[normalem]{ulem}'

local function envelopper(cmd, contenu)
  local res = { pandoc.RawInline("latex", "\\" .. cmd .. "{") }
  for _, el in ipairs(contenu) do table.insert(res, el) end
  table.insert(res, pandoc.RawInline("latex", "}"))
  return res
end

function Strikeout(el)
  return envelopper("sout", el.content)
end

function Underline(el)
  -- ulem ne gère pas l'imbrication : si le souligné contient du barré, on garde le barré seul
  for _, c in ipairs(el.content) do
    if c.t == "Strikeout" then return el.content end
  end
  return envelopper("uline", el.content)
end
