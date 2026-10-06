<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:local="urn:local-functions"
    exclude-result-prefixes="xsl local">
    <xsl:output method="html" indent="yes"/>

    <!-- Pad each dot-separated segment to 10 digits for correct OID sorting.
         e.g. "2.16.840.1.113883.5.2" becomes "0000000002.0000000016.0000000840..."
         Non-numeric suffixes like "-CP" on "2.16.840.1.113883.12.443-CP" are
         split at the hyphen so the OID part sorts numerically and the suffix
         sorts alphabetically after. -->
    <xsl:function name="local:pad-key">
        <xsl:param name="key"/>
        <xsl:choose>
            <xsl:when test="matches($key, '^\d')">
                <!-- Split on hyphen: OID part + optional suffix -->
                <xsl:variable name="oid" select="if (contains($key, '-')) then substring-before($key, '-') else $key"/>
                <xsl:variable name="suffix" select="if (contains($key, '-')) then concat('-', substring-after($key, '-')) else ''"/>
                <xsl:variable name="padded-segments" as="xs:string*" xmlns:xs="http://www.w3.org/2001/XMLSchema">
                    <xsl:for-each select="tokenize($oid, '\.')">
                        <xsl:sequence select="format-number(number(.), '0000000000')"/>
                    </xsl:for-each>
                </xsl:variable>
                <xsl:sequence select="concat('1', string-join($padded-segments, '.'), $suffix)"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:sequence select="concat('0', $key)"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:function>

    <!-- Sort key: en-us=0, nl-nl=1, everything else=2 -->
    <xsl:template name="lang-sort-prefix">
        <xsl:param name="lang"/>
        <xsl:choose>
            <xsl:when test="$lang = 'en-us'">0</xsl:when>
            <xsl:when test="$lang = 'nl-nl'">1</xsl:when>
            <xsl:otherwise>2</xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="translations">
        <html>
            <head>
                <title>CDA Language File</title>
                <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #333; line-height: 1.5; }
                    h1 { border-bottom: 1px solid #eee; padding-bottom: 10px; }
                    h2 { margin-top: 30px; }
                    table { border-collapse: collapse; width: 100%; margin: 10px 0; }
                    th, td { text-align: left; padding: 6px 10px; border: 1px solid #ddd; font-size: 13px; }
                    th { background: #f6f8fa; position: sticky; top: 0; }
                    tr:nth-child(even) { background: #f9f9f9; }
                    tr:hover { background: #fffde7; }
                    td:first-child { font-family: monospace; white-space: nowrap; }
                    .empty { color: #ccc; }
                </style>
            </head>
            <body>
                <h1>CDA Language File</h1>

                <h2>Supported Languages (<xsl:value-of select="count(languageList/language)"/>)</h2>
                <ul>
                    <xsl:for-each select="languageList/language">
                        <xsl:sort select="@lang"/>
                        <li>
                            <strong><xsl:value-of select="@lang"/></strong>
                            <xsl:text> &#8212; </xsl:text>
                            <xsl:value-of select="@description"/>
                        </li>
                    </xsl:for-each>
                </ul>

                <h2>Translation Keys (<xsl:value-of select="count(translation)"/>)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Key</th>
                            <xsl:for-each select="languageList/language">
                                <xsl:sort>
                                    <xsl:attribute name="select">
                                        <xsl:call-template name="lang-sort-prefix">
                                            <xsl:with-param name="lang" select="@lang"/>
                                        </xsl:call-template>
                                    </xsl:attribute>
                                </xsl:sort>
                                <xsl:sort select="@lang"/>
                                <xsl:variable name="lang" select="@lang"/>
                                <xsl:if test="../../translation/value[@lang = $lang]">
                                    <th>
                                        <xsl:value-of select="@lang"/>
                                        <xsl:text> (</xsl:text>
                                        <xsl:value-of select="count(../../translation/value[@lang = $lang])"/>
                                        <xsl:text>)</xsl:text>
                                    </th>
                                </xsl:if>
                            </xsl:for-each>
                        </tr>
                    </thead>
                    <tbody>
                        <xsl:for-each select="translation">
                            <xsl:sort select="local:pad-key(@key)"/>
                            <xsl:call-template name="render-translation"/>
                        </xsl:for-each>
                    </tbody>
                </table>
            </body>
        </html>
    </xsl:template>

    <xsl:template name="render-translation">
        <xsl:variable name="curPos" select="."/>
        <tr>
            <td><xsl:value-of select="@key"/></td>
            <xsl:for-each select="//languageList/language">
                <xsl:sort>
                    <xsl:attribute name="select">
                        <xsl:call-template name="lang-sort-prefix">
                            <xsl:with-param name="lang" select="@lang"/>
                        </xsl:call-template>
                    </xsl:attribute>
                </xsl:sort>
                <xsl:sort select="@lang"/>
                <xsl:variable name="lang" select="@lang"/>
                <xsl:if test="//translation/value[@lang = $lang]">
                    <td>
                        <xsl:choose>
                            <xsl:when test="$curPos/value[@lang = $lang]">
                                <xsl:value-of select="$curPos/value[@lang = $lang]"/>
                            </xsl:when>
                            <xsl:otherwise>
                                <xsl:attribute name="class">empty</xsl:attribute>
                                <xsl:text>&#8212;</xsl:text>
                            </xsl:otherwise>
                        </xsl:choose>
                    </td>
                </xsl:if>
            </xsl:for-each>
        </tr>
    </xsl:template>
</xsl:stylesheet>
